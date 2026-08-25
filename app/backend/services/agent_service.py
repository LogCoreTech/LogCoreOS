"""Agent loop — wraps tool-enabled AI completions over user data."""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from services import (
    auth_service,
    notes_service,
    priority_service,
    profile_service,
    push_service,
    task_service,
)
from services.ai_provider import agent_completion
from services.file_service import (
    brain_path,
    read_json,
    read_markdown,
    resolve_user_md_path,
    user_path,
    write_json,
    write_markdown,
    ws_path,
)

logger = logging.getLogger("logcore.agent")

MAX_STEPS = 10
_RUNS_CAP = 50
_PENDING_CAP = 20


def _brain_skip(user: dict) -> set[str]:
    """Same reasoning as routers/brain.py's own skip-list — a module's owned
    Brain paths are off-limits to the AI's generic list/read/search tools
    only while that module is disabled for THIS user (conditional, per-user,
    matching every module's own dual-access pattern — not just "never
    installed instance-wide"), unioned with the always-skipped Tasks folder
    (structurally different shape, JSON not markdown)."""
    from module_registry import brain_paths_for_disabled

    disabled = set(user.get("disabled_modules", []))
    return {"Tasks"} | brain_paths_for_disabled(disabled)


# Tools available in research mode — read-only access only
_RESEARCH_TOOLS = {
    "list_tasks",
    "get_top3_tasks",
    "get_scored_tasks",
    "list_brain_files",
    "read_brain_file",
    "get_profile",
    "list_notes",
    "read_note",
    "get_task_history",
    "search_brain",
    "get_week_snapshot",
    "search_web",
    "list_asset_templates",
    "list_assets",
    "search_assets",
    "list_finance_books",
    "list_finance_transactions",
    "get_finance_report",
    "get_budget_status",
    "get_balance_projection",
    "get_priorities",
    "list_contacts",
    "get_contact",
    "get_help",
    # admin read-only
    "list_users",
    "list_household_members",
    "list_shared_tasks",
    "read_system_file",
    "list_dashboards",
    "get_dashboard",
    "list_dashboard_templates",
    "get_dashboard_block_catalog",
}

# Tools that never modify data — safe to run without per-write approval in
# approve mode. Anything NOT listed here requires approval, so new tools are
# write-gated by default. ask_user_question has no side effects either — it
# pauses via its own dedicated mechanism (see run_agent), never the write-gate.
_READ_TOOLS = _RESEARCH_TOOLS | {"get_home_assistant_state", "ask_user_question"}

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic input_schema format — translated for OpenAI by ai_provider)
# ---------------------------------------------------------------------------

_USER_TOOLS: list[dict] = [
    {
        "name": "list_tasks",
        "description": "List all of the user's pending tasks with their full details.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "add_task",
        "description": "Add a new task for the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "category": {
                    "type": "string",
                    "description": "Category (e.g. Health, Work, Personal)",
                },
                "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "type": {"type": "string", "enum": ["todo", "recurring", "goal", "appointment"]},
                "recurrence": {"type": "string", "enum": ["daily", "weekly", "monthly"]},
                "due_date": {"type": "string", "description": "Due date YYYY-MM-DD"},
                "due_time": {"type": "string", "description": "Due time HH:MM (requires due_date)"},
                "notes": {"type": "string"},
                "asset_id": {
                    "type": "string",
                    "description": "Optional asset ID to link this task to (see list_assets)",
                },
            },
            "required": ["title", "category"],
        },
    },
    {
        "name": "update_task",
        "description": "Update an existing task by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to update"},
                "title": {"type": "string"},
                "category": {"type": "string"},
                "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "status": {"type": "string", "enum": ["pending", "done", "skipped"]},
                "due_date": {"type": "string"},
                "due_time": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_task",
        "description": "Delete a task by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to delete"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_top3_tasks",
        "description": "Get the top 3 highest-priority pending tasks.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_scored_tasks",
        "description": "Get all pending tasks sorted by priority score descending.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_brain_files",
        "description": "List all markdown files in the user's brain (notes, profile, memory, etc.).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_brain_file",
        "description": "Read the full contents of a brain markdown file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the .md file, e.g. 'Notes/MyNote.md'",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_brain_file",
        "description": "Overwrite an existing brain markdown file. File must already exist — use create_brain_file to make new ones.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to an existing .md file"},
                "content": {"type": "string", "description": "New full content of the file"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "create_brain_file",
        "description": "Create a new markdown file in the user's brain. Fails if the file already exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path for the new .md file, e.g. 'Notes/MyNote.md'",
                },
                "content": {"type": "string", "description": "Initial content (defaults to empty)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_notes",
        "description": (
            "List all notes and folders visible to the user: their own, the household/team pool's, "
            "and any shared with them by another user. A note from someone else carries an `_owner` "
            "field (a username, or 'household'/'team' for a pool note) and an `_access` field "
            "(read|contribute|edit) — own notes have neither. Pass the `_owner` you got back here into "
            "read_note/update_note/delete_note/move_note's own `owner` param so they resolve to the "
            "right store even if the same note name exists in more than one place."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_note",
        "description": "Read an existing note's content, including one shared with the user or in the household/team pool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative note path, e.g. 'Work/Meeting Notes'",
                },
                "owner": {
                    "type": "string",
                    "description": "Optional — the note's `_owner` field from list_notes, if it has one. Disambiguates when the same path could exist in more than one visible store.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "create_note",
        "description": "Create a new note in the user's own Notes folder. Path is relative to Notes/ without the .md extension, e.g. 'Work/Meeting Notes' or 'Ideas'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative note path, e.g. 'Work/Meeting Notes'",
                },
                "content": {
                    "type": "string",
                    "description": "Initial markdown content (defaults to empty)",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "update_note",
        "description": (
            "Overwrite an existing note's content — the user's own, or one shared with them at "
            "contribute/edit level. Use list_notes or read_note first if you need to see what's there."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative note path, e.g. 'Work/Meeting Notes'",
                },
                "content": {"type": "string", "description": "New full markdown content"},
                "owner": {
                    "type": "string",
                    "description": "Optional — the note's `_owner` field from list_notes, if it has one. Disambiguates when the same path could exist in more than one visible store.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "delete_note",
        "description": "Permanently delete a note by path — the user's own, or one shared with them at edit level.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative note path, e.g. 'Work/Meeting Notes'",
                },
                "owner": {
                    "type": "string",
                    "description": "Optional — the note's `_owner` field from list_notes, if it has one. Disambiguates when the same path could exist in more than one visible store.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_profile",
        "description": (
            "Read the user's full profile — their own Contact record (self_of the user). Fields include: "
            "occupation, gender, city, state, country, pronouns, wake_weekday, wake_weekend, bedtime, "
            "work_start, work_end, height_cm, height_unit, weight_kg, weight_unit, blood_type, diet, "
            "exercise, conditions, medications, marital_status, affiliated_contact_ids (linked family/"
            "company contacts), pets, income_range, budget_style, life_mission, "
            "core_values (list of short strings, not a single comma-separated string), "
            "key_constraints, communication_style, tone, response_language, topics_to_emphasize, "
            "topics_to_avoid, notes, priority_order ({personal: [...], business: [...]}), "
            "career_history (resume-style list: [{title, company_id, industry, education, "
            "years_experience, skills, start_date, end_date, archived}])."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_priorities",
        "description": (
            "Get the ordered life-priority categories (highest first) that weigh tasks and goals. "
            "Consult this BEFORE creating any task or goal so its category aligns with what matters "
            "most. scope 'user' (default) = the user's priorities for the active workspace; "
            "'household' or 'team' = the shared-pool priorities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["user", "household", "team"]},
            },
            "required": [],
        },
    },
    {
        "name": "get_help",
        "description": (
            "Read LogCore's in-app help guide to explain how a feature or module works. Call this "
            "whenever the user asks how to do something, seems confused, or asks what LogCore can do. "
            "Answer from what it returns and point them to the cited /help#<section> anchor. Pass a "
            "section id (e.g. 'finance', 'tasks', 'sharing', 'chat') to focus on one topic, or omit "
            "it to get the whole guide including the FAQ."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Optional help section id to focus on (e.g. finance, tasks, sharing).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_contacts",
        "description": (
            "List CRM contacts visible in the active workspace (own + shared + pool). "
            "Use `query` to search by name/email/tag. Returns id, name, type, emails, tags, status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "get_contact",
        "description": "Get one contact's full detail plus its interactions and deals, by contact id.",
        "input_schema": {
            "type": "object",
            "properties": {"contact_id": {"type": "string"}},
            "required": ["contact_id"],
        },
    },
    {
        "name": "create_contact",
        "description": (
            "Create a CRM contact. ALWAYS check for an existing match first — this tool "
            "auto-searches by name/email and returns the existing contact instead of creating a "
            "duplicate. Provide name (required), optional type (person|company), emails, phones, tags, notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": ["person", "company"]},
                "emails": {"type": "array", "items": {"type": "string"}},
                "phones": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "update_contact",
        "description": "Update fields on an existing contact by id (name, emails, phones, tags, status, notes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "fields": {"type": "object"},
            },
            "required": ["contact_id", "fields"],
        },
    },
    {
        "name": "log_interaction",
        "description": (
            "Log an interaction with a contact (call/email/meeting/text/note) with a summary and "
            "optional follow_up date (YYYY-MM-DD)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "type": {"type": "string", "enum": ["call", "email", "meeting", "text", "note"]},
                "summary": {"type": "string"},
                "follow_up": {"type": "string"},
            },
            "required": ["contact_id", "summary"],
        },
    },
    {
        "name": "create_deal",
        "description": "Create a deal on a contact: title (required), value_cents, and pipeline stage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "title": {"type": "string"},
                "value_cents": {"type": "integer"},
                "stage": {"type": "string"},
            },
            "required": ["contact_id", "title"],
        },
    },
    {
        "name": "update_profile",
        "description": (
            "Update one or more profile fields on the user's own Contact record. Pass only the fields you "
            "want to change — existing fields are preserved. "
            "Goals and completable items belong in tasks (type='goal'), not here. "
            "This is for biographical/aspirational context: life mission, values, health, family, work, AI preferences."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": 'Dict of profile fields to update, e.g. {"life_mission": "Run a marathon", "occupation": "Engineer"}',
                },
            },
            "required": ["fields"],
        },
    },
    {
        "name": "append_memory",
        "description": "Append a dated note to the user's Short-Term or Long-Term Memory file. Use short for recent context; long for stable facts worth keeping indefinitely.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Markdown text to append"},
                "target": {
                    "type": "string",
                    "enum": ["short", "long"],
                    "description": "Which memory file to append to (default: short)",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "rewrite_memory",
        "description": "Overwrite a memory file entirely with new condensed content. Use this to clean up or compress memory — not for adding new entries (use append_memory for that).",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Full new markdown content for the memory file",
                },
                "target": {
                    "type": "string",
                    "enum": ["short", "long"],
                    "description": "Which memory file to rewrite (default: short)",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "get_task_history",
        "description": "Get the user's completed tasks. Useful for weekly reviews, reflection, and tracking progress.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max number of tasks to return (default 20)",
                },
                "since_date": {
                    "type": "string",
                    "description": "Only return tasks completed on or after this date (YYYY-MM-DD)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_brain",
        "description": (
            "Search across the user's Brain markdown files (notes, journal, memory, profile) for a "
            "keyword or phrase. Notes shared with the user or in the household/team pool are searched "
            "too, alongside the user's own; journal/memory/profile search stays scoped to the user's "
            "own files, since those aren't shareable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Case-insensitive search term"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "move_note",
        "description": "Move or rename a note — the user's own, or one shared with them at edit level. Paths are relative to Notes/ without .md extension.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_path": {"type": "string", "description": "Current note path, e.g. 'Ideas'"},
                "to_path": {
                    "type": "string",
                    "description": "New note path, e.g. 'Brainstorms/Ideas'",
                },
                "owner": {
                    "type": "string",
                    "description": "Optional — the note's `_owner` field from list_notes, if it has one. Disambiguates when the same path could exist in more than one visible store.",
                },
            },
            "required": ["from_path", "to_path"],
        },
    },
    {
        "name": "create_note_folder",
        "description": "Create a folder inside the user's Notes directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Folder path relative to Notes/, e.g. 'Projects' or 'Projects/Work'",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "create_tasks",
        "description": "Create multiple tasks at once. Useful for planning sessions. Each task uses the same schema as add_task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "List of task objects to create",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "category": {"type": "string"},
                            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                            "type": {
                                "type": "string",
                                "enum": ["todo", "recurring", "goal", "appointment"],
                            },
                            "due_date": {"type": "string"},
                            "due_time": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                        "required": ["title", "category"],
                    },
                },
            },
            "required": ["tasks"],
        },
    },
    {
        "name": "send_notification",
        "description": "Send a push notification to the user via their configured ntfy channel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Notification title"},
                "body": {"type": "string", "description": "Notification body text"},
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "update_timezone",
        "description": "Update the user's timezone. Use an IANA timezone string, e.g. 'America/New_York', 'Europe/London', 'Asia/Tokyo'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "description": "IANA timezone string"},
            },
            "required": ["timezone"],
        },
    },
    {
        "name": "complete_shared_task",
        "description": "Mark a shared household task as done. Only works if you are the assigned member or an admin.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the shared task to mark complete",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "propose_plan",
        "description": (
            "Present a plan to the user for approval BEFORE taking any write actions "
            "(creating, updating, or deleting tasks, notes, files, or memory). "
            "Call this first. Do not call other write tools in the same turn — wait for the user to confirm."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Plain-English summary of what you're about to do",
                },
                "actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific steps you plan to take, e.g. ['Create task: Call dentist (Health, High priority)', 'Set due date to 2024-01-15']",
                },
            },
            "required": ["summary", "actions"],
        },
    },
    {
        "name": "ask_user_question",
        "description": (
            "Ask the user a clarifying multiple-choice question when their request is ambiguous or "
            "a real decision needs their input before you proceed — mirrors the ask-a-question tool "
            "available in coding-agent sessions. Use this instead of guessing or silently picking a "
            "default. Execution pauses in EVERY mode (including auto) until they answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask, ending in a question mark.",
                },
                "header": {
                    "type": "string",
                    "description": "A very short label for the question (max ~12 chars), e.g. 'Category' or 'Approach'.",
                },
                "options": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Short display text for this choice.",
                            },
                            "description": {
                                "type": "string",
                                "description": "What this option means or implies.",
                            },
                        },
                        "required": ["label", "description"],
                    },
                    "description": "2-4 choices, mutually exclusive unless multi_select is true.",
                },
                "multi_select": {
                    "type": "boolean",
                    "description": "True if the user may pick more than one option.",
                },
            },
            "required": ["question", "header", "options", "multi_select"],
        },
    },
    {
        "name": "get_week_snapshot",
        "description": "Get a full overview of the current week — tasks due this week, overdue tasks, and tasks completed this week. Use at the start of any planning or review session.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_suggestion",
        "description": "Immediately trigger a proactive suggestion by ID. Built-in IDs: 'daily_digest', 'overdue_alert', 'weekly_review', 'goal_drift'. Custom suggestions use their UUID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "suggestion_id": {
                    "type": "string",
                    "description": "Built-in name or custom UUID of the suggestion to run",
                },
            },
            "required": ["suggestion_id"],
        },
    },
    {
        "name": "update_suggestion",
        "description": "Enable/disable a suggestion or change its delivery settings. Built-in IDs: 'daily_digest', 'overdue_alert', 'weekly_review', 'goal_drift'. Custom suggestions use their UUID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "suggestion_id": {"type": "string", "description": "Built-in name or custom UUID"},
                "enabled": {"type": "boolean", "description": "Enable or disable this suggestion"},
                "delivery": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["push", "in_app", "chat"]},
                    "description": "Delivery channels",
                },
                "hour": {
                    "type": "integer",
                    "description": "Hour to fire (0-23, null = system default for built-ins)",
                },
                "days_threshold": {
                    "type": "integer",
                    "description": "Days without progress before goal_drift fires (goal_drift only)",
                },
            },
            "required": ["suggestion_id"],
        },
    },
    {
        "name": "create_suggestion",
        "description": (
            "Create a new recurring AI-powered suggestion. The AI will run your prompt on schedule and deliver the result. "
            "Schedule modes: 'daily' (every day at hour), 'interval' (every N days at hour, requires interval_days), "
            "'weekly' (specific weekday at hour, requires day_of_week like 'mon'–'sun')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short display name, e.g. 'Evening wind-down'",
                },
                "prompt": {
                    "type": "string",
                    "description": "Prompt sent to the AI when this suggestion fires",
                },
                "hour": {"type": "integer", "description": "Hour to fire (0-23)"},
                "delivery": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["push", "in_app", "chat"]},
                    "description": "Delivery channels (default: ['in_app'])",
                },
                "schedule": {
                    "type": "string",
                    "enum": ["daily", "interval", "weekly"],
                    "description": "Schedule type (default: 'daily')",
                },
                "interval_days": {
                    "type": "integer",
                    "description": "Required when schedule='interval': fire every N days",
                },
                "day_of_week": {
                    "type": "string",
                    "description": "Required when schedule='weekly': 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', or 'sun'",
                },
            },
            "required": ["name", "prompt", "hour"],
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the internet for current information, news, or any topic not in the user's Brain. "
            "Returns titles, URLs, and content snippets. Available in research mode."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Max results (default 5, max 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_asset_templates",
        "description": "List asset templates (the premade field structures, e.g. 'parcel'). Call this BEFORE creating or updating assets to learn valid template keys and field keys/types/options.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_assets",
        "description": "List assets visible to the user in the current workspace: their own, pool (team/household) assets, and assets shared with them. Assets form a tree via parent_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "template": {"type": "string", "description": "Filter by template key"},
                "include_archived": {"type": "boolean", "description": "Include archived assets"},
            },
            "required": [],
        },
    },
    {
        "name": "create_asset",
        "description": "Create an asset in the user's own store. Call list_asset_templates first — 'fields' keys must match the template's field keys exactly.",
        "input_schema": {
            "type": "object",
            "properties": {
                "template": {"type": "string", "description": "Template key, e.g. 'parcel'"},
                "name": {"type": "string", "description": "Asset name, e.g. 'Lot 12'"},
                "parent_id": {
                    "type": "string",
                    "description": "Optional parent asset ID for nesting",
                },
                "fields": {
                    "type": "object",
                    "description": "Field values keyed by the template's field keys",
                },
                "notes": {"type": "string"},
            },
            "required": ["template", "name"],
        },
    },
    {
        "name": "update_asset",
        "description": "Update an asset's name, notes, or field values by ID. Respects the user's access (read-only shares cannot be updated).",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "name": {"type": "string"},
                "fields": {
                    "type": "object",
                    "description": "Field values to merge; null deletes a key",
                },
                "notes": {"type": "string"},
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "archive_asset",
        "description": "Archive (or unarchive) an asset. Archiving hides the asset and its whole subtree from default views without deleting anything.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "archived": {
                    "type": "boolean",
                    "description": "true to archive (default), false to unarchive",
                },
                "cascade": {
                    "type": "boolean",
                    "description": "true to also (un)archive all descendants",
                },
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "search_assets",
        "description": "Search the assets visible to the user by a text query — matches asset name and field values. Use this instead of list_assets when looking for specific assets in a large collection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to match in name or field values"},
                "template": {"type": "string", "description": "Optional template key filter"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "move_asset",
        "description": "Move an asset to a new parent (or to the top level with parent_id null). Same owner only. Respects the user's edit access.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "parent_id": {
                    "type": "string",
                    "description": "New parent asset ID, or null for top level",
                },
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "list_finance_books",
        "description": "List the finance books visible to the user in the active workspace, with their accounts, computed balances (integer cents) and categories. Call this first to get book/account IDs for other finance tools.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_finance_transactions",
        "description": "List transactions in a finance book, newest first. Amounts are integer cents: positive = income, negative = expense.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "to": {"type": "string", "description": "End date YYYY-MM-DD"},
                "account_id": {"type": "string", "description": "Filter to one account"},
                "category": {"type": "string", "description": "Filter to one category name"},
                "query": {"type": "string", "description": "Text match on payee/notes"},
                "limit": {"type": "integer", "description": "Max results (default 50)"},
            },
            "required": ["book_id"],
        },
    },
    {
        "name": "get_finance_report",
        "description": "Monthly income vs expenses report for a finance book with a per-category breakdown. Amounts are integer cents. Defaults to the current month when month is omitted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "month": {"type": "string", "description": "Month YYYY-MM (default: current)"},
            },
            "required": ["book_id"],
        },
    },
    {
        "name": "get_budget_status",
        "description": "Budget status for a finance book: spent vs limit per budgeted category for a month. Amounts are integer cents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "month": {"type": "string", "description": "Month YYYY-MM (default: current)"},
            },
            "required": ["book_id"],
        },
    },
    {
        "name": "get_balance_projection",
        "description": "Projected balance for a finance account on a future date: current balance plus scheduled recurring bills/income and planned one-off items up to that date. Returns the itemized breakdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "account_id": {"type": "string", "description": "Account ID within the book"},
                "date": {"type": "string", "description": "Target date YYYY-MM-DD"},
            },
            "required": ["book_id", "account_id", "date"],
        },
    },
    {
        "name": "create_invoice",
        "description": "Create a draft invoice in a finance book. Amounts are integer cents. Requires edit access to the book; the user must approve this write.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "client_id": {
                    "type": "string",
                    "description": "Optional client ID from the book's client list",
                },
                "due_date": {"type": "string", "description": "Due date YYYY-MM-DD"},
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "qty": {"type": "number"},
                            "unit_cents": {"type": "integer"},
                        },
                        "required": ["description", "unit_cents"],
                    },
                },
                "tax_pct": {"type": "number", "description": "Tax percent 0-50 (default 0)"},
                "notes": {"type": "string"},
            },
            "required": ["book_id", "due_date", "line_items"],
        },
    },
    {
        "name": "add_finance_transaction",
        "description": "Log an income or expense transaction in a finance book. amount_cents is signed integer cents: positive = income, negative = expense. Respects the user's access (contribute-level users may be limited to expenses). The user must approve this write.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "account_id": {"type": "string", "description": "Account ID within the book"},
                "amount_cents": {
                    "type": "integer",
                    "description": "Signed cents: -4599 = $45.99 expense",
                },
                "date": {"type": "string", "description": "Date YYYY-MM-DD (default today)"},
                "category": {"type": "string", "description": "Category from the book (optional)"},
                "payee": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["book_id", "account_id", "amount_cents"],
        },
    },
    {
        "name": "categorize_transaction",
        "description": "Set the category on an existing finance transaction (e.g. filing bank-imported uncategorized entries). Learns a payee rule so future imports auto-categorize. The user must approve this write.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
                "tx_id": {
                    "type": "string",
                    "description": "Transaction ID (see list_finance_transactions)",
                },
                "category": {"type": "string", "description": "Category name from the book"},
            },
            "required": ["book_id", "tx_id", "category"],
        },
    },
    {
        "name": "mark_invoice_paid",
        "description": "Record a payment on an invoice (partial or full — omit amount_cents to pay the remaining balance). Optionally logs a linked income transaction when account_id is given. Requires edit access; the user must approve this write.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
                "invoice_id": {"type": "string"},
                "amount_cents": {
                    "type": "integer",
                    "description": "Payment amount in cents (default: remaining balance)",
                },
                "account_id": {
                    "type": "string",
                    "description": "Optional account to log the income transaction in",
                },
                "method": {"type": "string", "description": "check / transfer / cash / card"},
            },
            "required": ["book_id", "invoice_id"],
        },
    },
    # -- Dashboards (2026-08-09) --------------------------------------------
    {
        "name": "list_dashboards",
        "description": "List dashboards visible to the user (own + workspace pool + shared-to-them), each annotated with access level and, if applicable, its template.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_dashboard",
        "description": "Get one dashboard's blocks, including each one's current position and size on the desktop grid (36 columns wide, 24px rows) — call this before update_dashboard_block if you're moving or resizing an existing block, so you can see what's already occupied and pick a spot that doesn't overlap another block.",
        "input_schema": {
            "type": "object",
            "properties": {"dashboard_id": {"type": "string"}},
            "required": ["dashboard_id"],
        },
    },
    {
        "name": "list_dashboard_templates",
        "description": "List dashboard templates the user can build a new dashboard from (role-permitted global + their own personal + shared-and-accepted).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_dashboard_block_catalog",
        "description": "List every dashboard block type (label, category, admin_only) together with its config_fields — the exact keys/kinds needed to configure it for add_dashboard_block/update_dashboard_block. Call this before adding or editing a block if you don't already know its config shape.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "create_dashboard",
        "description": "Create a new dashboard, blank or from a template. pool=true creates a shared household/team dashboard (admin only) instead of a personal one.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "icon": {"type": "string", "description": "Optional emoji"},
                "template_id": {
                    "type": "string",
                    "description": "Optional — build from this template's block set",
                },
                "subject_id": {
                    "type": "string",
                    "description": "Required if the template has a subject_type — the contact or asset id this dashboard is about",
                },
                "pool": {
                    "type": "boolean",
                    "description": "true = shared household/team dashboard (admin only)",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "add_dashboard_block",
        "description": "Add a block to a dashboard. Requires contribute or edit access. Fails if the dashboard uses a template — its block set is template-controlled (edit the template instead, or use update_dashboard_template). Call get_dashboard_block_catalog first if you don't already know the block type's config shape. The new block is stacked at the bottom automatically — position (x/y) is never set here, only size is optionally controllable via `layout`.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "string"},
                "type": {
                    "type": "string",
                    "description": "A block type from get_dashboard_block_catalog",
                },
                "config": {
                    "type": "object",
                    "description": "Config keys per get_dashboard_block_catalog's config_fields for this type",
                },
                "layout": {
                    "type": "object",
                    "description": (
                        "Optional size override, in grid units — the desktop grid is 36 columns "
                        "wide, the mobile grid is 12 columns wide (always full-width there — "
                        "mobile is effectively one column), and each row unit is a fixed 24px "
                        "tall. Default size if omitted is 12 columns wide by 9 rows tall (roughly "
                        "a third of the desktop width). Use a wider `w` for a block with a lot of "
                        "horizontal content (a table, a wide chart) and a taller `h` for a block "
                        "with a long list. Position is always auto-stacked below the existing "
                        "blocks regardless of size."
                    ),
                    "properties": {
                        "w": {"type": "integer", "description": "Width in grid columns, 1-36"},
                        "h": {"type": "integer", "description": "Height in grid rows (24px each)"},
                    },
                },
            },
            "required": ["dashboard_id", "type", "config"],
        },
    },
    {
        "name": "update_dashboard_block",
        "description": "Replace one existing block's config, and optionally its position and/or size — position, size, card background, and header visibility are all yours to set here, not just the block's own data fields. Requires contribute or edit access. Fails if the dashboard uses a template. Call get_dashboard first if you're moving or resizing — it returns every block's current {x, y, w, h} on the desktop grid so you can pick a spot that doesn't land on top of another block. Nothing here checks for overlaps automatically; read the current layout and reason about it yourself, the same way a person dragging a block on screen can see what's already there.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "string"},
                "block_id": {"type": "string"},
                "config": {
                    "type": "object",
                    "description": (
                        "Config keys per get_dashboard_block_catalog's config_fields for this "
                        "type — REPLACES the block's entire current config, so re-send every key "
                        "you want kept, not just the ones you're changing (get_dashboard returns "
                        "the block's current config to start from). Every non-chromeless block "
                        "type accepts two extra booleans here regardless of its own data fields: "
                        "`show_card` (the card/border background) and `show_header` (the icon+label "
                        "header, when the dashboard isn't in edit mode) — both default to true when "
                        "omitted, so only send one to turn it off."
                    ),
                },
                "layout": {
                    "type": "object",
                    "description": (
                        "Optional position/size override, in grid units (36-column desktop "
                        "grid, 24px rows — see get_dashboard's `grid` field and each block's "
                        "own `layout`). Omit any key to leave that aspect of the block's "
                        "current layout untouched. `x`/`y` move it (top-left corner); `w`/`h` "
                        "resize it. Only the desktop layout is affected — mobile always stays "
                        "full-width and keeps its own stacking order regardless."
                    ),
                    "properties": {
                        "x": {
                            "type": "integer",
                            "description": "Left edge, in grid columns from 0",
                        },
                        "y": {"type": "integer", "description": "Top edge, in grid rows from 0"},
                        "w": {"type": "integer", "description": "Width in grid columns, 1-36"},
                        "h": {"type": "integer", "description": "Height in grid rows (24px each)"},
                    },
                },
            },
            "required": ["dashboard_id", "block_id", "config"],
        },
    },
    {
        "name": "remove_dashboard_block",
        "description": "Remove one block from a dashboard. Requires contribute or edit access. Fails if the dashboard uses a template.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "string"},
                "block_id": {"type": "string"},
            },
            "required": ["dashboard_id", "block_id"],
        },
    },
    {
        "name": "create_dashboard_template",
        "description": (
            "Create a dashboard template — a reusable block set that every dashboard built from it stays "
            "synced to (editing the template later updates all of them automatically). owner='me' creates "
            "a personal template (any user); owner='global' creates an instance-wide template (admin only). "
            "IMPORTANT: before creating a 'global' template, tell the user in your own words that this is an "
            "instance-wide shared object — every dashboard built from it updates immediately, including ones "
            "they can't see the contents of, and there's no automatic undo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "icon": {"type": "string", "description": "Optional emoji"},
                "subject_type": {
                    "type": "string",
                    "enum": ["contact", "asset"],
                    "description": "Optional — if set, every dashboard from this template picks one contact/asset as its subject",
                },
                "blocks": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": 'List of {type, config} — call get_dashboard_block_catalog for valid types/config shapes. A contact/asset-kind field may use the literal string "$subject" instead of a concrete id if subject_type matches, resolved per-dashboard at render time.',
                },
                "owner": {"type": "string", "enum": ["me", "global"]},
            },
            "required": ["label", "owner"],
        },
    },
    {
        "name": "update_dashboard_template",
        "description": (
            "Update a dashboard template's label, icon, subject_type, or full block list. Personal templates: "
            "owner only. Global templates: admin only. IMPORTANT: before updating a GLOBAL template, tell the "
            "user in your own words that this changes an instance-wide shared object — every dashboard built "
            "from it updates immediately, including ones they can't see the contents of, and there's no "
            "automatic undo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "template_id": {"type": "string"},
                "label": {"type": "string"},
                "icon": {"type": "string"},
                "subject_type": {"type": "string", "enum": ["contact", "asset"]},
                "blocks": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Full replacement list of {type, config} blocks",
                },
                "restrict_roles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Global templates only — feature roles allowed to use this template (empty = everyone)",
                },
            },
            "required": ["template_id"],
        },
    },
]

_ADMIN_TOOLS: list[dict] = [
    {
        "name": "list_users",
        "description": "List all users in the system with basic info (admin only).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_household_members",
        "description": "List the names of household members valid for shared task assignment (admin only). Call this before assigning a shared task if you are not certain of the exact member name.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_shared_tasks",
        "description": "List all shared household tasks (admin only).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "add_shared_task",
        "description": "Add a task to the shared household list (admin only).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "category": {"type": "string"},
                "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "due_date": {"type": "string"},
                "notes": {"type": "string"},
                "assigned_to": {
                    "type": "string",
                    "description": "Name of the member responsible for this task. Must match a real household member — first names are matched automatically; if the name is ambiguous or unknown the tool returns an error listing valid members, and you should ask the user which member they meant.",
                },
            },
            "required": ["title", "category"],
        },
    },
    {
        "name": "update_shared_task",
        "description": "Update a shared household task (admin only). Members can only check tasks off via complete_shared_task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to update"},
                "title": {"type": "string"},
                "category": {"type": "string"},
                "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "due_date": {"type": "string"},
                "due_time": {"type": "string"},
                "notes": {"type": "string"},
                "assigned_to": {
                    "type": "string",
                    "description": "Reassign to a different member. Must match a real household member; ambiguous or unknown names return an error listing valid members.",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_shared_task",
        "description": "Delete a shared household task (admin only).",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to delete"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "read_system_file",
        "description": "Read a system-level Brain file that applies to all users (admin only). Use update_profile for personal AI preferences instead.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "enum": ["SOUL.md", "AGENTS.md", "USERS.md", "MEMORY_MAP.md"],
                    "description": "System Brain file to read",
                },
            },
            "required": ["filename"],
        },
    },
    {
        "name": "update_system_file",
        "description": "Overwrite a system-level Brain file (admin only). Changes affect all users. Use with care.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "enum": ["SOUL.md", "AGENTS.md", "USERS.md", "MEMORY_MAP.md"],
                    "description": "System Brain file to update",
                },
                "content": {"type": "string", "description": "Full new markdown content"},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "run_tests",
        "description": "Run the backend test suite (pytest) and return the output. Admin only. Use to check that the codebase is healthy after making changes.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "delete_asset",
        "description": "Permanently delete an asset by ID (admin only). Fails if the asset has children. Prefer archive_asset unless the user explicitly wants permanent deletion.",
        "input_schema": {
            "type": "object",
            "properties": {"asset_id": {"type": "string"}},
            "required": ["asset_id"],
        },
    },
    {
        "name": "create_asset_template",
        "description": "Create an asset template (admin only). Fields are an ordered list of {key, label, type, options?, default?}; types: text, number, date, boolean, select.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Slug key, e.g. 'parcel' (immutable)"},
                "label": {"type": "string"},
                "icon": {"type": "string", "description": "Optional emoji"},
                "fields": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Ordered field definitions: {key, label, type, options?, default?}",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "update_asset_template",
        "description": "Update an asset template's label, icon, or full field list (admin only). The key is immutable. Changing fields affects every asset using this template — confirm with the user first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "label": {"type": "string"},
                "icon": {"type": "string"},
                "fields": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Full replacement list of field definitions",
                },
            },
            "required": ["key"],
        },
    },
]


def _module_tool_dispatch() -> dict[str, tuple[str, Callable]]:
    """{tool_name: (module_id, execute_fn)} built fresh from every ACTIVE
    module's agent_tools.py. O(1) dispatch for the executor's fallback case,
    rather than iterating modules and calling each in turn. Computed fresh
    (not cached at import time) so it reflects live install state, same
    reasoning as everything else install-state-dependent in this system."""
    from module_registry import active_manifests

    dispatch: dict[str, tuple[str, Callable]] = {}
    for module_id, manifest in active_manifests().items():
        if not manifest.owned_agent_tools:
            continue
        try:
            import importlib

            mod = importlib.import_module(f"module_packages.{module_id}.backend.agent_tools")
        except Exception:
            logger.exception(
                "module_packages/%s: agent_tools failed to import — its tools unavailable",
                module_id,
            )
            continue
        for tool_name in manifest.owned_agent_tools:
            dispatch[tool_name] = (module_id, mod.execute)
    return dispatch


def _module_tool_schemas() -> list[dict]:
    """Tool schemas contributed by every ACTIVE module's agent_tools.py."""
    from module_registry import active_manifests

    schemas: list[dict] = []
    for module_id, manifest in active_manifests().items():
        if not manifest.owned_agent_tools:
            continue
        try:
            import importlib

            mod = importlib.import_module(f"module_packages.{module_id}.backend.agent_tools")
            schemas.extend(mod.TOOL_SCHEMAS)
        except Exception:
            logger.exception(
                "module_packages/%s: agent_tools schemas failed to load", module_id
            )
    return schemas


def _get_tools(user: dict) -> list[dict]:
    from services.ha_service import is_configured as _ha_configured

    _HA_TOOL_NAMES = {
        "get_home_assistant_state",
        "control_home_assistant_device",
        "activate_scene",
        "trigger_home_assistant_automation",
    }
    ha_ok = _ha_configured()
    disabled = set(user.get("disabled_modules", []))
    tools = list(_USER_TOOLS)

    # Module-contributed tools: hard-gated by disabled_modules, same as every
    # other enforcement-gap fix in this system — a disabled/uninstalled
    # module's tools are never even offered to the model, so it can never
    # attempt a call that's guaranteed to fail (see help_service's
    # capabilities_index() for the SEPARATE, softer "the AI knows this
    # module exists but isn't installed" awareness channel).
    from module_registry import discover_manifests

    manifests, _errors = discover_manifests()
    owned_by_disabled: set[str] = set()
    for module_id, manifest in manifests.items():
        if module_id in disabled:
            owned_by_disabled.update(manifest.owned_agent_tools)
    tools.extend(t for t in _module_tool_schemas() if t["name"] not in owned_by_disabled)

    # The 4 HA tools (module-contributed via home_assistant/ since 2026-08-24)
    # need HA to actually be *configured*, not just installed+enabled —
    # installed only means the module's code is wired in; configured means
    # an admin has set a URL+token in Admin → Hosting. Applied as a final
    # pass over the combined list so it's agnostic to which source a tool's
    # schema came from.
    tools = [t for t in tools if ha_ok or t["name"] not in _HA_TOOL_NAMES]

    if user.get("role") == "admin":
        tools.extend(_ADMIN_TOOLS)
    return tools


# ---------------------------------------------------------------------------
# Member name resolution (shared task assignment)
# ---------------------------------------------------------------------------


def _resolve_member_name(raw: str) -> tuple[str | None, str | None]:
    """Resolve a (possibly partial) name against real member names.

    Returns (resolved_name, error). Exactly one of the two is set.
    Matching order: exact full name, exact first name, then first-name prefix —
    all case-insensitive. Ambiguous or unknown names return an error message
    that lists the candidates so the agent can ask the user.
    """
    query = raw.strip().lower()
    names = [u["name"] for u in auth_service.list_users()]
    if not query:
        return None, "assigned_to cannot be empty. Members: " + ", ".join(names)

    exact = [n for n in names if n.lower() == query]
    if len(exact) == 1:
        return exact[0], None

    first_name = [n for n in names if n.split()[0].lower() == query]
    if len(first_name) == 1:
        return first_name[0], None

    prefix = [n for n in names if n.split()[0].lower().startswith(query)]
    if len(prefix) == 1:
        return prefix[0], None

    candidates = exact or first_name or prefix
    if candidates:
        return None, (
            f"Ambiguous member name {raw!r} — matches: "
            + ", ".join(sorted(candidates))
            + ". Ask the user which member they meant."
        )
    return None, (
        f"No household member matching {raw!r}. Members: "
        + ", ".join(sorted(names))
        + ". Ask the user which member they meant — do not guess."
    )


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


def _resolve_note_or_error(user: dict, workspace: str, path: str, owner: str | None, need: str):
    """Resolve a note/folder path the agent's caller can reach at >= `need`
    access, the same way routers/notes.py's own _resolve() does for real
    users. Returns (store_user, None) on success or (None, error_dict)."""
    try:
        found = notes_service.find_note_store(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            path,
            owner=owner,
        )
    except ValueError as e:
        return None, {"error": str(e)}
    if not found:
        return None, {"error": f"Note not found: {path!r}"}
    store_user, access = found
    if not notes_service.meets(access, need):
        return None, {"error": f"You only have {access} access to {path!r} — that's not enough."}
    return store_user, None


_LG_COLS = 36  # DashboardGrid.jsx's COLS.lg — desktop grid width
_MAX_ROWS = 60  # generous cap (24px/row = 1440px tall) against a garbage/huge value
_MAX_Y = 500  # generous cap against a garbage/huge stacking position


def _block_layout_for_agent(block: dict) -> dict:
    """The desktop-grid position/size get_dashboard exposes to the agent
    (2026-08-15) — lg only, since that's the one breakpoint the agent can
    meaningfully reason about and control; sm always mirrors it at
    full-width, never independently interesting to read or set here."""
    lg = block.get("layout", {}).get("lg") or {}
    return {"x": lg.get("x", 0), "y": lg.get("y", 0), "w": lg.get("w", 12), "h": lg.get("h", 9)}


def _clamp_block_layout_override(override: dict, *, allow_position: bool, current_w: int) -> dict:
    """Clamp an agent-supplied {x?, y?, w?, h?} override to sane grid bounds
    (2026-08-15) — the agent can request a position/size, but never a
    nonsense one (zero/negative, wider than the desktop grid itself, or
    starting past its right edge). `allow_position` is False for
    add_dashboard_block (new blocks always auto-stack; see
    _apply_layout_override) and True for update_dashboard_block. `current_w`
    is the block's existing width, used to bound `x` when the override
    doesn't also change `w` — without it, an x-only move would wrongly clamp
    against the full grid width instead of the block's real (possibly much
    narrower) current width, pinning x to 0 for anything already narrower
    than full-width (caught by test_update_dashboard_block_can_move_position
    before this shipped)."""
    result = {}
    w = override.get("w")
    if isinstance(w, int) and not isinstance(w, bool):
        result["w"] = max(1, min(w, _LG_COLS))
    h = override.get("h")
    if isinstance(h, int) and not isinstance(h, bool):
        result["h"] = max(1, min(h, _MAX_ROWS))
    if allow_position:
        x = override.get("x")
        if isinstance(x, int) and not isinstance(x, bool):
            # Clamped against the resulting width (the override's own new w,
            # or else the block's current w) so the block can never be
            # placed hanging off the right edge.
            max_x = max(0, _LG_COLS - result.get("w", current_w))
            result["x"] = max(0, min(x, max_x))
        y = override.get("y")
        if isinstance(y, int) and not isinstance(y, bool):
            result["y"] = max(0, min(y, _MAX_Y))
    return result


def _apply_layout_override(layout: dict, override: dict, *, allow_position: bool = False) -> dict:
    """Apply a clamped {x?, y?, w?, h?} override onto a stacked_layout()-
    shaped {lg, sm} dict. Width/x only ever change on `lg` (the 36-col
    desktop grid; `sm` stays full-width at x=0, since mobile is effectively
    one column); height changes on both so the block reads the same tall on
    either breakpoint. `sm`'s own y is left untouched — mobile stacking order
    isn't something the agent has any way to reason about from the desktop
    grid it's shown, so an lg-only y change doesn't attempt to also guess a
    corresponding mobile position. Position (x/y) is only ever applied when
    allow_position=True (update_dashboard_block) — add_dashboard_block always
    auto-stacks new blocks via dashboards_service.stacked_layout()."""
    current_w = (layout.get("lg") or {}).get("w", _LG_COLS)
    clamped = _clamp_block_layout_override(
        override or {}, allow_position=allow_position, current_w=current_w
    )
    if not clamped:
        return layout
    result = {bp: dict(v) for bp, v in layout.items()}
    if "w" in clamped:
        result["lg"]["w"] = clamped["w"]
    if "h" in clamped:
        for bp in result:
            result[bp]["h"] = clamped["h"]
    if "x" in clamped:
        result["lg"]["x"] = clamped["x"]
    if "y" in clamped:
        result["lg"]["y"] = clamped["y"]
    return result


def _execute_tool(
    name: str,
    inputs: dict,
    user: dict,
    workspace: str = "personal",
    cross_workspace: bool = False,
) -> Any:
    """Run one tool; return result or an error dict — never raises."""
    try:
        match name:
            case "list_tasks":
                return task_service.list_tasks(user["name"])

            case "add_task":
                return task_service.add_task(user["name"], inputs)

            case "update_task":
                task_id = inputs["task_id"]
                updates = {k: v for k, v in inputs.items() if k != "task_id"}
                result = task_service.update_task(user["name"], task_id, updates)
                if result is None:
                    return {"error": f"Task {task_id!r} not found"}
                return result

            case "delete_task":
                ok = task_service.delete_task(user["name"], inputs["task_id"])
                return {"deleted": ok}

            case "get_top3_tasks":
                return priority_service.get_top3(user["name"])

            case "get_scored_tasks":
                return priority_service.get_all_scored(user["name"])

            case "list_brain_files":
                base = ws_path(user["name"], workspace)
                if not base.exists():
                    return []
                files = []
                skip = _brain_skip(user)
                for p in sorted(base.rglob("*.md")):
                    rel = p.relative_to(base)
                    if not any(part in skip for part in rel.parts):
                        files.append({"path": str(rel), "name": p.name})
                return files

            case "read_brain_file":
                raw = inputs["path"].lstrip("/")
                parts = raw.split("/")
                if any(p in ("", ".", "..") for p in parts) or not raw.endswith(".md"):
                    return {"error": "Access denied"}
                base = ws_path(user["name"], workspace)
                candidate = (base / raw).resolve()
                if not candidate.is_relative_to(user_path(user["name"]).resolve()):
                    return {"error": "Access denied"}
                if not candidate.exists():
                    return {"error": f"File not found: {inputs['path']!r}"}
                return read_markdown(candidate)

            case "write_brain_file":
                path = resolve_user_md_path(user["name"], inputs["path"])
                if not path.exists():
                    return {
                        "error": f"File not found: {inputs['path']!r}. Use create_brain_file for new files."
                    }
                write_markdown(path, inputs["content"])
                return {"ok": True}

            case "create_brain_file":
                path = resolve_user_md_path(user["name"], inputs["path"])
                if path.exists():
                    return {
                        "error": f"File already exists: {inputs['path']!r}. Use write_brain_file to edit it."
                    }
                write_markdown(path, inputs.get("content", ""))
                return {"ok": True, "created": inputs["path"]}

            case "list_notes":
                return notes_service.list_visible_notes(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                )

            case "read_note":
                store_user, err = _resolve_note_or_error(
                    user, workspace, inputs["path"], inputs.get("owner"), "read"
                )
                if err:
                    return err
                note = notes_service.get_note(store_user, inputs["path"], workspace)
                return note or {"error": f"Note not found: {inputs['path']!r}"}

            case "create_note":
                return notes_service.create_note(
                    user["name"], inputs["path"], inputs.get("content", ""), workspace
                )

            case "update_note":
                store_user, err = _resolve_note_or_error(
                    user, workspace, inputs["path"], inputs.get("owner"), "contribute"
                )
                if err:
                    return err
                result = notes_service.update_note(
                    store_user, inputs["path"], inputs["content"], workspace
                )
                return result or {"error": f"Note not found: {inputs['path']!r}"}

            case "delete_note":
                store_user, err = _resolve_note_or_error(
                    user, workspace, inputs["path"], inputs.get("owner"), "edit"
                )
                if err:
                    return err
                ok = notes_service.delete_note(store_user, inputs["path"], workspace)
                return {"deleted": ok}

            case "get_profile":
                from services import contacts_service

                return contacts_service.get_self_contact(user["name"], create_if_missing=True)

            case "get_help":
                from services import help_service

                return {"help": help_service.as_text(inputs.get("section") or None)}

            case "get_priorities":
                scope = inputs.get("scope", "user")
                if scope in ("household", "team"):
                    pool = "_household" if scope == "household" else "_team"
                    return {"scope": scope, "order": profile_service.get_priority_order(pool)}
                return {
                    "scope": workspace,
                    "order": profile_service.get_priority_order(user["name"], workspace),
                }

            case "list_contacts":
                from services import contacts_service

                out = contacts_service.list_visible_contacts(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                )
                q = (inputs.get("query") or "").strip().lower()
                if q:
                    out = [
                        c
                        for c in out
                        if q in c.get("name", "").lower()
                        or any(q in e.lower() for e in c.get("emails", []))
                        or any(q in t.lower() for t in c.get("tags", []))
                    ]
                return [
                    {
                        "id": c["id"],
                        "name": c.get("name"),
                        "type": c.get("type"),
                        "emails": c.get("emails", []),
                        "tags": c.get("tags", []),
                        "status": c.get("status", ""),
                    }
                    for c in out[:100]
                ]

            case "get_contact":
                from services import contacts_service

                found = contacts_service.find_contact(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["contact_id"],
                )
                if not found:
                    return {"error": "Contact not found"}
                store_user, contact, _access = found
                ws = contacts_service.effective_workspace(store_user, contact, workspace)
                return {
                    "contact": contact,
                    "interactions": contacts_service.list_interactions(
                        store_user, ws, contact["id"]
                    ),
                    "deals": contacts_service.list_deals(store_user, ws, contact["id"]),
                }

            case "create_contact":
                from services import contacts_service

                email = (inputs.get("emails") or [""])[0] if inputs.get("emails") else ""
                existing = contacts_service.find_match(
                    user["name"], workspace, name=inputs.get("name", ""), email=email
                )
                if existing:
                    return {
                        "existing": True,
                        "contact_id": existing["id"],
                        "message": f"A contact named {existing['name']} already exists — reusing it.",
                    }
                contact = contacts_service.create_contact(
                    user["name"], workspace, inputs, created_by=user["name"]
                )
                return {"created": True, "contact_id": contact["id"]}

            case "update_contact":
                from services import contacts_service

                found = contacts_service.find_contact(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["contact_id"],
                )
                if not found:
                    return {"error": "Contact not found"}
                store_user, contact, access = found
                if access != "edit":
                    return {"error": "You don't have edit access to this contact"}
                ws = contacts_service.effective_workspace(store_user, contact, workspace)
                updated = contacts_service.update_contact(
                    store_user,
                    ws,
                    inputs["contact_id"],
                    inputs.get("fields", {}),
                    viewer=user["name"],
                )
                return {"updated": bool(updated)}

            case "log_interaction":
                from services import contacts_service

                found = contacts_service.find_contact(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["contact_id"],
                )
                if not found:
                    return {"error": "Contact not found"}
                store_user, contact, access = found
                if access not in ("edit", "contribute"):
                    return {"error": "You don't have access to add to this contact"}
                ws = contacts_service.effective_workspace(store_user, contact, workspace)
                item = contacts_service.add_interaction(
                    store_user, ws, inputs["contact_id"], inputs, created_by=user["name"]
                )
                return {"logged": True, "interaction_id": item["id"]}

            case "create_deal":
                from services import contacts_service

                found = contacts_service.find_contact(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["contact_id"],
                )
                if not found:
                    return {"error": "Contact not found"}
                store_user, contact, access = found
                if access not in ("edit", "contribute"):
                    return {"error": "You don't have access to add to this contact"}
                ws = contacts_service.effective_workspace(store_user, contact, workspace)
                deal = contacts_service.add_deal(
                    store_user, ws, inputs["contact_id"], inputs, created_by=user["name"]
                )
                return {"created": True, "deal_id": deal["id"]}

            case "update_profile":
                from services import contacts_service

                self_contact = contacts_service.get_self_contact(
                    user["name"], create_if_missing=True
                )
                try:
                    return contacts_service.update_contact(
                        contacts_service.POOL_HOUSEHOLD,
                        "personal",
                        self_contact["id"],
                        inputs.get("fields", {}),
                    )
                except ValueError as exc:
                    return {"error": str(exc)}

            case "append_memory":
                from datetime import date

                target = inputs.get("target", "short")
                fname = "Long_Term_Memory.md" if target == "long" else "Short_Term_Memory.md"
                mem_path = ws_path(user["name"], workspace) / fname
                today = date.today().isoformat()
                existing = mem_path.read_text() if mem_path.exists() else ""
                safe_content = inputs["content"].replace("</brain_data>", "[/brain_data]")
                updated = existing.rstrip() + f"\n\n## {today}\n\n{safe_content}\n"
                write_markdown(mem_path, updated)
                return {"ok": True, "target": fname}

            case "rewrite_memory":
                target = inputs.get("target", "short")
                fname = "Long_Term_Memory.md" if target == "long" else "Short_Term_Memory.md"
                mem_path = ws_path(user["name"], workspace) / fname
                safe_content = inputs["content"].replace("</brain_data>", "[/brain_data]")
                write_markdown(mem_path, safe_content)
                return {"ok": True, "target": fname}

            case "get_task_history":
                limit = int(inputs.get("limit", 20))
                since = inputs.get("since_date")
                history = task_service.list_history(user["name"], limit=limit)
                if since:
                    history = [t for t in history if (t.get("completed_at") or "") >= since]
                return history

            case "search_brain":
                query = inputs["query"].lower()
                personal_base = user_path(user["name"])
                business_base = personal_base / "Business"
                if cross_workspace:
                    search_roots = [
                        ("personal", personal_base),
                        ("business", business_base),
                    ]
                else:
                    search_roots = [(workspace, ws_path(user["name"], workspace))]

                def _snippet(text: str) -> str | None:
                    idx = text.lower().find(query)
                    if idx == -1:
                        return None
                    start = max(0, idx - 100)
                    end = min(len(text), idx + 200)
                    return text[start:end].strip()

                results = []
                skip = _brain_skip(user)
                for ws_label, base in search_roots:
                    if not base.exists():
                        continue
                    for p in sorted(base.rglob("*.md")):
                        rel = p.relative_to(base)
                        if any(part in skip for part in rel.parts):
                            continue
                        try:
                            text = p.read_text()
                        except OSError:
                            continue
                        snippet = _snippet(text)
                        if snippet is None:
                            continue
                        path_label = f"{ws_label}/{rel}" if cross_workspace else str(rel)
                        results.append({"path": path_label, "snippet": snippet, "owner": None})

                # Shared/pool notes — own files above are covered by the rglob
                # walk; journal/memory/profile stay own-files-only since none
                # of those are shareable.
                for ws_label, _base in search_roots:
                    visible = notes_service.list_visible_notes(
                        user["name"],
                        user.get("feature_role", "member"),
                        user.get("role") == "admin",
                        ws_label,
                        include_archived=True,
                    )
                    for item in visible:
                        owner = item.get("_owner")
                        if not owner or item.get("type") != "note":
                            continue
                        store_user = notes_service.store_for_owner(owner, user["name"])
                        note = notes_service.get_note(store_user, item["path"], ws_label)
                        if not note:
                            continue
                        snippet = _snippet(note.get("content") or "")
                        if snippet is None:
                            continue
                        # Matches the own-files path label above exactly (full
                        # brain-relative, with the Notes/ prefix and .md
                        # extension) — read_note/update_note still want the
                        # bare Notes-relative form, same pre-existing gap a
                        # model already has to bridge for its own search hits.
                        note_rel = f"Notes/{item['path']}.md"
                        path_label = f"{ws_label}/{note_rel}" if cross_workspace else note_rel
                        results.append({"path": path_label, "snippet": snippet, "owner": owner})
                return results

            case "move_note":
                store_user, err = _resolve_note_or_error(
                    user, workspace, inputs["from_path"], inputs.get("owner"), "edit"
                )
                if err:
                    return err
                return notes_service.move_item(
                    store_user, inputs["from_path"], inputs["to_path"], "note", workspace
                )

            case "create_note_folder":
                return notes_service.create_folder(user["name"], inputs["path"], workspace)

            case "create_tasks":
                created = []
                for t in inputs.get("tasks", []):
                    created.append(task_service.add_task(user["name"], t))
                return created

            case "send_notification":
                sent = push_service.send_push(user["name"], inputs["title"], inputs["body"])
                return {"sent": sent}

            case "update_timezone":
                from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

                try:
                    ZoneInfo(inputs["timezone"])
                except (ZoneInfoNotFoundError, KeyError):
                    return {"error": f"Invalid timezone: {inputs['timezone']!r}"}
                u = auth_service.get_user_by_name(user["name"])
                if not u:
                    return {"error": "User not found"}
                auth_service.update_user(u["id"], {"timezone": inputs["timezone"]})
                return {"ok": True, "timezone": inputs["timezone"]}

            case "propose_plan":
                # Only ever reached via the resume path once approved — run_agent
                # itself intercepts the call to pause for confirmation before this
                # executes (2026-08-09; was a bare echo relying entirely on the
                # system prompt telling the model to wait, the same shape of gap
                # the approve-mode replay bug had).
                return {"status": "approved"}

            case "get_week_snapshot":
                today = auth_service.today_for_user(user["name"])
                week_start = today - timedelta(days=today.weekday())
                week_end = week_start + timedelta(days=6)
                ws, we, ts = week_start.isoformat(), week_end.isoformat(), today.isoformat()
                all_tasks = task_service.list_tasks(user["name"])
                completed = task_service.list_history(user["name"], limit=50)
                return {
                    "week_start": ws,
                    "week_end": we,
                    "due_this_week": [
                        t for t in all_tasks if ws <= (t.get("due_date") or "") <= we
                    ],
                    "overdue": [t for t in all_tasks if t.get("due_date") and t["due_date"] < ts],
                    "no_date": [t for t in all_tasks if not t.get("due_date")],
                    "completed_this_week": [
                        t for t in completed if ws <= (t.get("completed_at") or "")[:10] <= we
                    ],
                }

            case "complete_shared_task":
                task = task_service.get_task("_household", inputs["task_id"])
                if task is None:
                    return {"error": f"Shared task {inputs['task_id']!r} not found"}
                if user.get("role") != "admin" and task.get("assigned_to") != user["name"]:
                    return {"error": "Not authorized — you can only complete tasks assigned to you"}
                result = task_service.update_task(
                    "_household",
                    inputs["task_id"],
                    {
                        "status": "done",
                        "completed_by": user["name"],
                    },
                )
                return result or {"error": "Update failed"}

            case "list_users":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                from services.auth_service import _load_auth

                safe = {"id", "name", "email", "role", "timezone"}
                return [{k: v for k, v in u.items() if k in safe} for u in _load_auth()["users"]]

            case "list_household_members":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                return [{"name": u["name"]} for u in auth_service.list_users()]

            case "list_shared_tasks":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                return task_service.list_tasks("_household")

            case "add_shared_task":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                if inputs.get("assigned_to") is not None:
                    resolved, err = _resolve_member_name(inputs["assigned_to"])
                    if err:
                        return {"error": err}
                    inputs = {**inputs, "assigned_to": resolved}
                return task_service.add_task("_household", inputs)

            case "update_shared_task":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                task_id = inputs["task_id"]
                updates = {k: v for k, v in inputs.items() if k != "task_id"}
                if updates.get("assigned_to") is not None:
                    resolved, err = _resolve_member_name(updates["assigned_to"])
                    if err:
                        return {"error": err}
                    updates["assigned_to"] = resolved
                result = task_service.update_task("_household", task_id, updates)
                if result is None:
                    return {"error": f"Shared task {task_id!r} not found"}
                return result

            case "delete_shared_task":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                ok = task_service.delete_task("_household", inputs["task_id"])
                return {"deleted": ok}

            case "list_asset_templates":
                from services import assets_service

                return assets_service.visible_templates(
                    user["name"],
                    is_admin=user.get("role") == "admin",
                    feature_role=user.get("feature_role", "member"),
                )

            case "list_assets":
                from services import assets_service

                items = assets_service.list_visible(
                    user["name"],
                    workspace,
                    include_archived=bool(inputs.get("include_archived")),
                    is_admin=user.get("role") == "admin",
                    pool_edit=user.get("pool_edit") or [],
                    viewer_role=user.get("feature_role") or "",
                )
                if inputs.get("template"):
                    items = [a for a in items if a.get("template") == inputs["template"]]
                # History is noise for the model — drop it from tool output
                return [{k: v for k, v in a.items() if k != "history"} for a in items]

            case "create_asset":
                from services import assets_service

                return assets_service.create_asset(
                    user["name"], inputs, workspace=workspace, created_by=user["name"]
                )

            case "update_asset":
                from services import assets_service

                found = assets_service.find_asset(
                    user["name"],
                    workspace,
                    inputs["asset_id"],
                    is_admin=user.get("role") == "admin",
                    pool_edit=user.get("pool_edit") or [],
                    viewer_role=user.get("feature_role") or "",
                )
                if found is None:
                    return {"error": f"Asset {inputs['asset_id']!r} not found"}
                if not found["can_edit"]:
                    return {"error": "Read-only access — you cannot update this asset"}
                updates = {k: v for k, v in inputs.items() if k != "asset_id"}
                result = assets_service.update_asset(
                    found["store"],
                    inputs["asset_id"],
                    updates,
                    workspace=found["store_workspace"],
                    by=user["name"],
                )
                return result or {"error": "Asset not found"}

            case "archive_asset":
                from services import assets_service

                found = assets_service.find_asset(
                    user["name"],
                    workspace,
                    inputs["asset_id"],
                    is_admin=user.get("role") == "admin",
                    pool_edit=user.get("pool_edit") or [],
                    viewer_role=user.get("feature_role") or "",
                )
                if found is None:
                    return {"error": f"Asset {inputs['asset_id']!r} not found"}
                if not found["can_manage"]:
                    return {"error": "Only the owner or a pool manager can archive this asset"}
                result = assets_service.set_archived(
                    found["store"],
                    inputs["asset_id"],
                    bool(inputs.get("archived", True)),
                    workspace=found["store_workspace"],
                    by=user["name"],
                    cascade=bool(inputs.get("cascade", False)),
                )
                return result or {"error": "Asset not found"}

            case "search_assets":
                from services import assets_service

                items = assets_service.list_visible(
                    user["name"],
                    workspace,
                    is_admin=user.get("role") == "admin",
                    pool_edit=user.get("pool_edit") or [],
                    viewer_role=user.get("feature_role") or "",
                )
                if inputs.get("template"):
                    items = [a for a in items if a.get("template") == inputs["template"]]
                q = str(inputs.get("query", "")).strip().lower()
                if q:

                    def _match(a: dict) -> bool:
                        if q in (a.get("name") or "").lower():
                            return True
                        return any(q in str(v).lower() for v in (a.get("fields") or {}).values())

                    items = [a for a in items if _match(a)]
                return [{k: v for k, v in a.items() if k != "history"} for a in items]

            case "move_asset":
                from services import assets_service

                found = assets_service.find_asset(
                    user["name"],
                    workspace,
                    inputs["asset_id"],
                    is_admin=user.get("role") == "admin",
                    pool_edit=user.get("pool_edit") or [],
                    viewer_role=user.get("feature_role") or "",
                )
                if found is None:
                    return {"error": f"Asset {inputs['asset_id']!r} not found"}
                if not found["can_edit"]:
                    return {"error": "Read-only access — you cannot move this asset"}
                result = assets_service.update_asset(
                    found["store"],
                    inputs["asset_id"],
                    {"parent_id": inputs.get("parent_id")},
                    workspace=found["store_workspace"],
                    by=user["name"],
                )
                return result or {"error": "Asset not found"}

            case "list_finance_books":
                from services import finance_service

                books = finance_service.list_visible_books(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                )
                out = []
                for book in books:
                    store = finance_service.store_for_annotated(book, user["name"], workspace)
                    summary = finance_service.book_summary(store, workspace, book)
                    # Share/audience fields are noise for the model
                    slim = {
                        k: v
                        for k, v in book.items()
                        if k not in ("shared_with", "contributors", "hidden_from")
                    }
                    slim["balances"] = summary["balances"]
                    slim["total_cents"] = summary["total_cents"]
                    out.append(slim)
                return out

            case "list_finance_transactions":
                from services import finance_service

                found_book = finance_service.find_book(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["book_id"],
                )
                if found_book is None:
                    return {"error": f"Finance book {inputs['book_id']!r} not found"}
                store, book, _access = found_book
                items, total = finance_service.list_transactions(
                    store,
                    workspace,
                    book["id"],
                    date_from=inputs.get("from"),
                    date_to=inputs.get("to"),
                    account_id=inputs.get("account_id"),
                    category=inputs.get("category"),
                    query=inputs.get("query"),
                    limit=min(int(inputs.get("limit") or 50), 200),
                )
                return {"items": items, "total": total}

            case "get_finance_report":
                from services import finance_reports, finance_service

                found_book = finance_service.find_book(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["book_id"],
                )
                if found_book is None:
                    return {"error": f"Finance book {inputs['book_id']!r} not found"}
                store, book, _access = found_book
                month = inputs.get("month") or datetime.now().strftime("%Y-%m")
                return finance_reports.monthly_report(store, workspace, book, month)

            case "get_budget_status":
                from services import finance_planning_service, finance_service

                found_book = finance_service.find_book(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["book_id"],
                )
                if found_book is None:
                    return {"error": f"Finance book {inputs['book_id']!r} not found"}
                store, book, _access = found_book
                month = inputs.get("month") or datetime.now().strftime("%Y-%m")
                return finance_planning_service.budget_status(store, workspace, book, month)

            case "get_balance_projection":
                from services import finance_planning_service, finance_service

                found_book = finance_service.find_book(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["book_id"],
                )
                if found_book is None:
                    return {"error": f"Finance book {inputs['book_id']!r} not found"}
                store, book, _access = found_book
                return finance_planning_service.project_balance(
                    store, workspace, book, inputs["account_id"], inputs["date"]
                )

            case "add_finance_transaction":
                from services import finance_planning_service, finance_service

                found_book = finance_service.find_book(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["book_id"],
                )
                if found_book is None:
                    return {"error": f"Finance book {inputs['book_id']!r} not found"}
                store, book, access = found_book
                amount = inputs.get("amount_cents")
                if access == "contribute":
                    caps = (
                        finance_service.resolve_caps(
                            user["name"],
                            user.get("feature_role", "member"),
                            user.get("role") == "admin",
                            store,
                            book,
                            inputs.get("account_id"),
                            workspace,
                        )
                        or {}
                    )
                    kind = "income" if (amount or 0) > 0 else "expense"
                    if kind not in caps.get("add", []):
                        return {"error": f"Your access doesn't allow adding {kind} entries"}
                elif access != "edit":
                    return {"error": "Read-only access — you cannot add transactions here"}
                tx = finance_service.add_transaction(
                    store,
                    workspace,
                    book,
                    {
                        "date": inputs.get("date") or datetime.now().strftime("%Y-%m-%d"),
                        "amount_cents": amount,
                        "account_id": inputs.get("account_id"),
                        "category": inputs.get("category", ""),
                        "payee": inputs.get("payee", ""),
                        "notes": inputs.get("notes", ""),
                    },
                    created_by=user["name"],
                )
                finance_planning_service.on_transactions_added(store, workspace, book["id"], [tx])
                return tx

            case "categorize_transaction":
                from services import finance_service

                found_book = finance_service.find_book(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["book_id"],
                )
                if found_book is None:
                    return {"error": f"Finance book {inputs['book_id']!r} not found"}
                store, book, access = found_book
                tx = finance_service.get_transaction(store, workspace, book["id"], inputs["tx_id"])
                if not tx:
                    return {"error": f"Transaction {inputs['tx_id']!r} not found"}
                if access == "contribute" and tx.get("created_by") != user["name"]:
                    return {"error": "You can only categorize entries you created"}
                if access not in ("edit", "contribute"):
                    return {"error": "Read-only access — you cannot categorize here"}
                result = finance_service.update_transaction(
                    store, workspace, book, inputs["tx_id"], {"category": inputs["category"]}
                )
                if result and result.get("payee") and result.get("source") in ("simplefin", "csv"):
                    finance_service.learn_rule(
                        store, workspace, book["id"], result["payee"], inputs["category"]
                    )
                return result or {"error": "Transaction not found"}

            case "create_invoice":
                from services import finance_invoice_service, finance_service

                found_book = finance_service.find_book(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["book_id"],
                )
                if found_book is None:
                    return {"error": f"Finance book {inputs['book_id']!r} not found"}
                store, book, access = found_book
                if access != "edit":
                    return {"error": "Read-only access — you cannot create invoices here"}
                return finance_invoice_service.create_invoice(
                    store,
                    workspace,
                    book["id"],
                    {
                        "client_id": inputs.get("client_id"),
                        "due_date": inputs["due_date"],
                        "line_items": inputs.get("line_items") or [],
                        "tax_pct": inputs.get("tax_pct", 0),
                        "notes": inputs.get("notes", ""),
                    },
                    created_by=user["name"],
                )

            case "mark_invoice_paid":
                from services import finance_invoice_service, finance_service

                found_book = finance_service.find_book(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    workspace,
                    inputs["book_id"],
                )
                if found_book is None:
                    return {"error": f"Finance book {inputs['book_id']!r} not found"}
                store, book, access = found_book
                if access != "edit":
                    return {"error": "Read-only access — you cannot record payments here"}
                invoice = finance_invoice_service.get_invoice(
                    store, workspace, book["id"], inputs["invoice_id"]
                )
                if not invoice:
                    return {"error": f"Invoice {inputs['invoice_id']!r} not found"}
                amount = inputs.get("amount_cents") or invoice["balance_cents"]
                if amount <= 0:
                    return {"error": "Invoice already has a zero balance"}
                return finance_invoice_service.record_payment(
                    store,
                    workspace,
                    book["id"],
                    inputs["invoice_id"],
                    {
                        "amount_cents": amount,
                        "account_id": inputs.get("account_id"),
                        "method": inputs.get("method", ""),
                    },
                    created_by=user["name"],
                )

            case "delete_asset":
                from services import assets_service

                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                found = assets_service.find_asset(
                    user["name"], workspace, inputs["asset_id"], is_admin=True
                )
                if found is None:
                    return {"error": f"Asset {inputs['asset_id']!r} not found"}
                ok = assets_service.delete_asset(
                    found["store"], inputs["asset_id"], workspace=found["store_workspace"]
                )
                return {"deleted": ok}

            case "create_asset_template":
                from services import assets_service

                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                # Admin chat manages GLOBAL templates.
                return assets_service.create_template(inputs, owner=assets_service.GLOBAL_OWNER)

            case "update_asset_template":
                from services import assets_service

                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                tmpl = assets_service.get_global_template(inputs["key"])
                if tmpl is None:
                    return {"error": f"Global template {inputs['key']!r} not found"}
                updates = {k: v for k, v in inputs.items() if k != "key"}
                result = assets_service.update_template(tmpl["id"], updates)
                return result or {"error": f"Template {inputs['key']!r} not found"}

            case "read_system_file":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                _ALLOWED_SYSTEM = {"SOUL.md", "AGENTS.md", "USERS.md", "MEMORY_MAP.md"}
                fname = inputs["filename"]
                if fname not in _ALLOWED_SYSTEM:
                    return {"error": f"Not an allowed system file: {fname!r}"}
                p = brain_path() / fname
                if not p.exists():
                    return {"error": f"{fname} not found"}
                return read_markdown(p)

            case "update_system_file":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                _ALLOWED_SYSTEM = {"SOUL.md", "AGENTS.md", "USERS.md", "MEMORY_MAP.md"}
                fname = inputs["filename"]
                if fname not in _ALLOWED_SYSTEM:
                    return {"error": f"Not an allowed system file: {fname!r}"}
                safe_content = inputs["content"].replace("</brain_data>", "[/brain_data]")
                write_markdown(brain_path() / fname, safe_content)
                return {"ok": True, "updated": fname}

            case "run_suggestion":
                # This tool executor is called synchronously inside the agent loop.
                # For custom suggestions (which need async AI calls), we use a thread pool to run asyncio.
                import concurrent.futures

                from services import suggestions_service as sug_svc

                sid = inputs["suggestion_id"]
                cfg = sug_svc.get_config(user["name"])
                is_custom = any(c["id"] == sid for c in cfg.get("custom", []))
                if is_custom:
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        fut = pool.submit(sug_svc.run_suggestion_sync, user["name"], sid)
                        return fut.result(timeout=60)
                return sug_svc.run_suggestion_sync(user["name"], sid)

            case "update_suggestion":
                from services import suggestions_service as sug_svc

                sid = inputs["suggestion_id"]
                updates = {k: v for k, v in inputs.items() if k != "suggestion_id"}
                if not updates:
                    return {"error": "No fields to update"}
                return sug_svc.update_config(user["name"], sid, updates)

            case "create_suggestion":
                import scheduler as sched_mod  # noqa: PLC0415
                from services import suggestions_service as sug_svc

                new_s = sug_svc.create_custom(user["name"], inputs)
                if new_s.get("enabled", True):
                    try:
                        sched_mod.add_custom_job(user["name"], new_s)
                    except Exception:
                        pass
                return new_s

            case "run_tests":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                import subprocess
                from pathlib import Path as _Path

                backend_dir = _Path(__file__).parent.parent
                result = subprocess.run(
                    ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"],
                    capture_output=True,
                    text=True,
                    cwd=backend_dir,
                    timeout=120,
                )
                output = result.stdout + (result.stderr if result.returncode != 0 else "")
                return {
                    "passed": result.returncode == 0,
                    "output": output.strip(),
                }

            case "search_web":
                from services.web_search_service import search as _web_search

                q = inputs["query"]
                n = int(inputs.get("max_results", 5))
                return _web_search(q, n)

            # -- Dashboards (2026-08-09) -----------------------------------
            case "list_dashboards":
                from services import dashboards_service

                return dashboards_service.list_visible_dashboards(
                    user["name"],
                    user.get("feature_role") or "member",
                    user.get("role") == "admin",
                    workspace,
                )

            case "get_dashboard":
                from services import dashboards_service

                found = dashboards_service.find_dashboard(
                    user["name"],
                    user.get("feature_role") or "member",
                    user.get("role") == "admin",
                    workspace,
                    inputs["dashboard_id"],
                )
                if found is None:
                    return {
                        "error": f"Dashboard {inputs['dashboard_id']!r} not found or not accessible"
                    }
                d = found["dashboard"]
                return {
                    "id": d["id"],
                    "name": d["name"],
                    "icon": d["icon"],
                    "template_id": d.get("template_id"),
                    "access": found["access"],
                    "grid": {"cols": _LG_COLS, "row_px": 24},
                    "blocks": [
                        {
                            "id": b["id"],
                            "type": b["type"],
                            "config": b["config"],
                            "layout": _block_layout_for_agent(b),
                        }
                        for b in d["blocks"]
                    ],
                }

            case "list_dashboard_templates":
                from services import dashboard_templates_service

                return dashboard_templates_service.visible_templates(
                    user["name"], user.get("role") == "admin", user.get("feature_role") or "member"
                )

            case "get_dashboard_block_catalog":
                from services.dashboard_blocks.agent_schemas import get_config_fields
                from services.dashboard_blocks.registry import catalog

                is_admin = user.get("role") == "admin"
                return [
                    {**c, "config_fields": get_config_fields(c["type"])} for c in catalog(is_admin)
                ]

            case "create_dashboard":
                from services import dashboards_service

                if inputs.get("pool") and user.get("role") != "admin":
                    return {"error": "Admin access required to create a pool dashboard"}
                is_pool = bool(inputs.get("pool"))
                store_user = dashboards_service.pool_for(workspace) if is_pool else user["name"]
                # Pool pseudo-users always store at the "personal" ws_path
                # base regardless of which workspace they're paired with —
                # same fix as routers/dashboards.py's create endpoint
                # (2026-08-18); this tool had the identical bug.
                store_ws = "personal" if is_pool else workspace
                d = dashboards_service.create_dashboard(
                    store_user,
                    store_ws,
                    user["name"],
                    inputs["name"],
                    inputs.get("icon") or "📊",
                    template_id=inputs.get("template_id"),
                    subject_id=inputs.get("subject_id"),
                )
                return {"id": d["id"], "name": d["name"], "icon": d["icon"]}

            case "add_dashboard_block":
                from services import dashboards_service
                from services.dashboard_blocks.registry import REGISTRY

                found = dashboards_service.find_dashboard(
                    user["name"],
                    user.get("feature_role") or "member",
                    user.get("role") == "admin",
                    workspace,
                    inputs["dashboard_id"],
                )
                if found is None:
                    return {
                        "error": f"Dashboard {inputs['dashboard_id']!r} not found or not accessible"
                    }
                if found["access"] not in ("edit", "contribute"):
                    return {"error": "Read-only access — you cannot add blocks to this dashboard"}
                dashboard = found["dashboard"]
                if dashboard.get("template_id"):
                    return {
                        "error": "This dashboard's block set comes from a template — use "
                        "update_dashboard_template to change its blocks, or detach it from the "
                        "template first."
                    }
                if inputs["type"] not in REGISTRY:
                    return {
                        "error": f"Unknown block type {inputs['type']!r} — call get_dashboard_block_catalog"
                    }
                new_block = {
                    "id": str(uuid.uuid4()),
                    "type": inputs["type"],
                    "config": inputs.get("config") or {},
                    "layout": _apply_layout_override(
                        dashboards_service.stacked_layout(dashboard["blocks"]),
                        inputs.get("layout"),
                    ),
                }
                updated = dashboards_service.update_dashboard(
                    found["store"],
                    found["store_workspace"],
                    inputs["dashboard_id"],
                    {"blocks": dashboard["blocks"] + [new_block]},
                    by=user["name"],
                )
                return {
                    "ok": True,
                    "block_id": new_block["id"],
                    "blocks": [
                        {"id": b["id"], "type": b["type"], "config": b["config"]}
                        for b in updated["blocks"]
                    ],
                }

            case "update_dashboard_block":
                from services import dashboards_service

                found = dashboards_service.find_dashboard(
                    user["name"],
                    user.get("feature_role") or "member",
                    user.get("role") == "admin",
                    workspace,
                    inputs["dashboard_id"],
                )
                if found is None:
                    return {
                        "error": f"Dashboard {inputs['dashboard_id']!r} not found or not accessible"
                    }
                if found["access"] not in ("edit", "contribute"):
                    return {
                        "error": "Read-only access — you cannot update blocks on this dashboard"
                    }
                dashboard = found["dashboard"]
                if dashboard.get("template_id"):
                    return {
                        "error": "This dashboard's block set comes from a template — use "
                        "update_dashboard_template to change its blocks."
                    }
                target = next(
                    (b for b in dashboard["blocks"] if b["id"] == inputs["block_id"]), None
                )
                if target is None:
                    return {"error": f"Block {inputs['block_id']!r} not found on this dashboard"}
                new_layout = (
                    _apply_layout_override(target["layout"], inputs["layout"], allow_position=True)
                    if inputs.get("layout")
                    else target["layout"]
                )
                new_blocks = [
                    (
                        {**b, "config": inputs["config"], "layout": new_layout}
                        if b["id"] == inputs["block_id"]
                        else b
                    )
                    for b in dashboard["blocks"]
                ]
                updated = dashboards_service.update_dashboard(
                    found["store"],
                    found["store_workspace"],
                    inputs["dashboard_id"],
                    {"blocks": new_blocks},
                    by=user["name"],
                )
                return {
                    "ok": True,
                    "blocks": [
                        {"id": b["id"], "type": b["type"], "config": b["config"]}
                        for b in updated["blocks"]
                    ],
                }

            case "remove_dashboard_block":
                from services import dashboards_service

                found = dashboards_service.find_dashboard(
                    user["name"],
                    user.get("feature_role") or "member",
                    user.get("role") == "admin",
                    workspace,
                    inputs["dashboard_id"],
                )
                if found is None:
                    return {
                        "error": f"Dashboard {inputs['dashboard_id']!r} not found or not accessible"
                    }
                if found["access"] not in ("edit", "contribute"):
                    return {
                        "error": "Read-only access — you cannot remove blocks from this dashboard"
                    }
                dashboard = found["dashboard"]
                if dashboard.get("template_id"):
                    return {
                        "error": "This dashboard's block set comes from a template — use "
                        "update_dashboard_template to change its blocks."
                    }
                if not any(b["id"] == inputs["block_id"] for b in dashboard["blocks"]):
                    return {"error": f"Block {inputs['block_id']!r} not found on this dashboard"}
                new_blocks = [b for b in dashboard["blocks"] if b["id"] != inputs["block_id"]]
                updated = dashboards_service.update_dashboard(
                    found["store"],
                    found["store_workspace"],
                    inputs["dashboard_id"],
                    {"blocks": new_blocks},
                    by=user["name"],
                )
                return {
                    "ok": True,
                    "blocks": [
                        {"id": b["id"], "type": b["type"], "config": b["config"]}
                        for b in updated["blocks"]
                    ],
                }

            case "create_dashboard_template":
                from services import dashboard_templates_service

                owner_param = inputs.get("owner", "me")
                if owner_param == "global" and user.get("role") != "admin":
                    return {"error": "Admin access required to create a global template"}
                owner = (
                    dashboard_templates_service.GLOBAL_OWNER
                    if owner_param == "global"
                    else user["name"]
                )
                return dashboard_templates_service.create_template(
                    {
                        "label": inputs.get("label"),
                        "icon": inputs.get("icon"),
                        "subject_type": inputs.get("subject_type"),
                        "blocks": inputs.get("blocks") or [],
                    },
                    owner=owner,
                )

            case "update_dashboard_template":
                from services import dashboard_templates_service

                found = dashboard_templates_service._find_template(inputs["template_id"])
                if found is None:
                    return {"error": f"Template {inputs['template_id']!r} not found"}
                owner, _tmpl = found
                is_global = owner == dashboard_templates_service.GLOBAL_OWNER
                if is_global and user.get("role") != "admin":
                    return {"error": "Admin access required to update a global template"}
                if not is_global and owner != user["name"]:
                    return {"error": "You can only update your own personal templates"}
                updates = {k: v for k, v in inputs.items() if k != "template_id"}
                result = dashboard_templates_service.update_template(inputs["template_id"], updates)
                return result or {"error": f"Template {inputs['template_id']!r} not found"}

            case _:
                dispatch = _module_tool_dispatch()
                entry = dispatch.get(name)
                if entry is not None:
                    _module_id, execute_fn = entry
                    result = execute_fn(name, inputs, user)
                    if result is not None:
                        return result
                return {"error": f"Unknown tool: {name!r}"}

    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Tool error: {exc}"}


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


async def run_agent(
    user: dict,
    goal: str,
    history: list[dict],
    system: str,
    mode: str = "plan",
    workspace: str = "personal",
    cross_workspace: bool = False,
    resume: dict | None = None,
    max_steps: int | None = None,
    chat_id: str | None = None,
) -> dict:
    """Run the agent loop and return a run record.

    `resume` replays a previously-paused turn instead of starting fresh: `messages`
    comes from the persisted pending-turn record (`goal`/`history` are ignored), the
    paused tool call(s) are executed/answered/declined exactly as originally
    proposed — never re-derived from the model's own prior text — and the loop then
    continues normally so the model can react to the result. `resume["kind"]` is
    `"write"` (execute via `_execute_tool`, or synthesize a declined result if
    `resume["decision"] == "decline"`) or `"question"` (use `resume["answer"]` as
    the tool result — the "tool" here is the human, nothing to execute).
    """
    run_id = (resume or {}).get("run_id") or str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    # Drop the pending_write/pending_question/pending_plan entry being resolved
    # right now — it's what's *about* to be replayed/answered below, not still
    # open. Leaving it in would leak a resolved pause into a later, genuinely
    # completed response's steps: the frontend's pendingWrites/pendingQuestion
    # detection doesn't cross-check `mode`, so it would render a phantom
    # approval card with no real run_id behind it (the completed response
    # never carries one) — clicking it sends `resume.run_id: undefined`, which
    # JSON.stringify drops entirely, and the API 422s with "field required".
    steps: list[dict] = [
        s
        for s in (resume or {}).get("steps", [])
        if s.get("type") not in ("pending_write", "pending_question", "pending_plan")
    ]
    tools_used = False
    final_answer = ""
    status = "completed"
    last_text = ""
    step_limit = max_steps if max_steps is not None else MAX_STEPS

    if resume:
        messages = list(resume["messages"])
        replay_results = []
        for tc in resume["pending_tool_calls"]:
            if resume.get("kind") == "question":
                result: Any = {"answer": resume.get("answer")}
            elif resume.get("decision") == "decline":
                result = {"declined": True}
            else:
                result = _execute_tool(
                    tc["name"],
                    tc["input"],
                    user,
                    workspace=workspace,
                    cross_workspace=cross_workspace,
                )
            steps.append(
                {
                    "type": "tool_call",
                    "tool": tc["name"],
                    "input": tc["input"],
                    "output": result,
                    "step": 0,
                }
            )
            result_str = json.dumps(result) if not isinstance(result, str) else result
            replay_results.append(
                {"type": "tool_result", "tool_use_id": tc["id"], "content": result_str}
            )
        messages.append({"role": "user", "content": replay_results})
        tools_used = True
    else:
        messages = list(history) + [{"role": "user", "content": goal}]

    all_tools = _get_tools(user)
    if mode in ("auto", "approve"):
        active_tools = [t for t in all_tools if t["name"] != "propose_plan"]
    elif mode == "research":
        from module_registry import read_only_agent_tool_names

        research_tools = _RESEARCH_TOOLS | read_only_agent_tool_names()
        active_tools = [t for t in all_tools if t["name"] in research_tools]
    else:  # plan
        active_tools = all_tools

    for step_num in range(step_limit):
        response = await agent_completion(
            system, messages, active_tools, user_name=user["name"], workspace=workspace
        )
        last_text = response.text

        if not response.tool_calls or response.stop_reason != "tool_use":
            final_answer = response.text
            if response.stop_reason == "max_tokens":
                status = "max_steps_reached"
            break

        # A clarifying question pauses in EVERY mode, checked before the
        # approve-mode write-gate below — if the model asks a question alongside
        # a write call in the same turn, the question always wins (nothing about
        # answering a question is mode-dependent the way a write is).
        ask_call = next((tc for tc in response.tool_calls if tc.name == "ask_user_question"), None)
        if ask_call:
            if response.text:
                steps.append({"type": "thought", "content": response.text, "step": step_num})
            steps.append(
                {
                    "type": "pending_question",
                    "question": ask_call.input.get("question"),
                    "header": ask_call.input.get("header"),
                    "options": ask_call.input.get("options"),
                    "multi_select": ask_call.input.get("multi_select", False),
                    "step": step_num,
                }
            )
            messages.append({"role": "assistant", "content": response.raw_content})
            save_pending_turn(
                user["name"],
                {
                    "run_id": run_id,
                    "chat_id": chat_id,
                    "kind": "question",
                    "mode": mode,
                    "goal": goal,
                    "messages": messages,
                    "pending_tool_calls": [
                        {"id": ask_call.id, "name": ask_call.name, "input": ask_call.input}
                    ],
                    "steps": steps,
                    "workspace": workspace,
                    "cross_workspace": cross_workspace,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            status = "awaiting_answer"
            final_answer = response.text or "I have a question before continuing."
            break

        # A proposed plan pauses the same way — propose_plan is only ever
        # offered in plan mode (see active_tools above), and used to be a bare
        # echo relying entirely on the system prompt telling the model to
        # wait, the same shape of gap the approve-mode replay bug had.
        plan_call = next((tc for tc in response.tool_calls if tc.name == "propose_plan"), None)
        if plan_call:
            if response.text:
                steps.append({"type": "thought", "content": response.text, "step": step_num})
            steps.append(
                {
                    "type": "pending_plan",
                    "summary": plan_call.input.get("summary"),
                    "actions": plan_call.input.get("actions", []),
                    "step": step_num,
                }
            )
            messages.append({"role": "assistant", "content": response.raw_content})
            save_pending_turn(
                user["name"],
                {
                    "run_id": run_id,
                    "chat_id": chat_id,
                    "kind": "plan",
                    "mode": mode,
                    "goal": goal,
                    "messages": messages,
                    "pending_tool_calls": [
                        {"id": plan_call.id, "name": plan_call.name, "input": plan_call.input}
                    ],
                    "steps": steps,
                    "workspace": workspace,
                    "cross_workspace": cross_workspace,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            status = "awaiting_approval"
            final_answer = (
                response.text or "Here's my plan — let me know if you'd like me to proceed."
            )
            break

        # Approve mode: pause before any write — nothing in this response is
        # executed; the frontend shows the pending writes for user approval.
        if mode == "approve":
            from module_registry import read_only_agent_tool_names

            read_tools = _READ_TOOLS | read_only_agent_tool_names()
            pending = [tc for tc in response.tool_calls if tc.name not in read_tools]
            if pending:
                if response.text:
                    steps.append({"type": "thought", "content": response.text, "step": step_num})
                for tc in pending:
                    steps.append(
                        {
                            "type": "pending_write",
                            "tool": tc.name,
                            "input": tc.input,
                            "step": step_num,
                        }
                    )
                # Persist exactly what was proposed so Approve replays this precise
                # call instead of the model re-guessing from its own prior text
                # (the original bug — see docs/MEMORY.md 2026-08-09 for the writeup).
                messages.append({"role": "assistant", "content": response.raw_content})
                save_pending_turn(
                    user["name"],
                    {
                        "run_id": run_id,
                        "chat_id": chat_id,
                        "kind": "write",
                        "mode": mode,
                        "goal": goal,
                        "messages": messages,
                        "pending_tool_calls": [
                            {"id": tc.id, "name": tc.name, "input": tc.input} for tc in pending
                        ],
                        "steps": steps,
                        "workspace": workspace,
                        "cross_workspace": cross_workspace,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                status = "awaiting_approval"
                final_answer = response.text or "I need your approval to make these changes."
                break

        # Tool-use turn
        tools_used = True
        if response.text:
            steps.append({"type": "thought", "content": response.text, "step": step_num})

        messages.append({"role": "assistant", "content": response.raw_content})

        tool_results = []
        for tc in response.tool_calls:
            step_entry: dict = {
                "type": "tool_call",
                "tool": tc.name,
                "input": tc.input,
                "step": step_num,
            }
            steps.append(step_entry)

            result = _execute_tool(
                tc.name, tc.input, user, workspace=workspace, cross_workspace=cross_workspace
            )
            step_entry["output"] = result

            result_str = json.dumps(result) if not isinstance(result, str) else result
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result_str,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    else:
        status = "max_steps_reached"
        final_answer = last_text or "Reached maximum steps."

    if tools_used and status == "completed":
        status = "agent"

    run = {
        "id": run_id,
        "goal": (resume or {}).get("goal", goal),
        "status": status,
        "steps": steps,
        "final_answer": final_answer,
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "step_count": sum(1 for s in steps if s["type"] == "tool_call"),
    }

    if tools_used:
        _save_run(user["name"], run)

    return run


def _save_run(user_name: str, run: dict) -> None:
    path = user_path(user_name) / "agent" / "runs.json"
    data = read_json(path, default={"runs": []})
    data["runs"].insert(0, run)
    data["runs"] = data["runs"][:_RUNS_CAP]
    write_json(path, data)


def _pending_turns_path(user_name: str):
    return user_path(user_name) / "agent" / "pending_turns.json"


def save_pending_turn(user_name: str, pending: dict) -> None:
    """Persist a paused turn (write approval or, later, a question) so a resume
    request can replay/answer the exact thing that was proposed. Not prefixed
    private since routers/chat.py calls this directly on the pause path."""
    path = _pending_turns_path(user_name)
    data = read_json(path, default={"pending": []})
    # A run can only ever have one live pending turn — replace, don't accumulate.
    data["pending"] = [p for p in data["pending"] if p["run_id"] != pending["run_id"]]
    data["pending"].insert(0, pending)
    data["pending"] = data["pending"][:_PENDING_CAP]
    write_json(path, data)


def load_pending_turn(user_name: str, run_id: str) -> dict | None:
    data = read_json(_pending_turns_path(user_name), default={"pending": []})
    return next((p for p in data["pending"] if p["run_id"] == run_id), None)


def get_pending_turn_by_chat_id(user_name: str, chat_id: str) -> dict | None:
    """The live pending_write/pending_question/pending_plan card for one
    conversation, if it currently has one — reopening a saved chat archive
    (a plain .md, no structured step data) previously lost this entirely:
    the assistant's prompt text ("I need your approval...") reloaded fine,
    but the actual interactive card (and its run_id, needed to act on it)
    did not, so a paused approval/question/plan effectively vanished on
    reload with no way to act on it except starting over (2026-08-15).
    `routers/chat.py`'s GET /chat/pending/{chat_id} re-attaches this record's
    `steps`/`mode`/`run_id` onto the last message when Chat.jsx reopens a
    session whose chat_sessions.json status is awaiting_approval/awaiting_answer."""
    data = read_json(_pending_turns_path(user_name), default={"pending": []})
    return next((p for p in data["pending"] if p.get("chat_id") == chat_id), None)


def delete_pending_turn(user_name: str, run_id: str) -> None:
    """Consume a pending turn so it can't be replayed twice (e.g. a double-submit
    of the Approve click) — called once, right after a successful load."""
    path = _pending_turns_path(user_name)
    data = read_json(path, default={"pending": []})
    data["pending"] = [p for p in data["pending"] if p["run_id"] != run_id]
    write_json(path, data)


# ---------------------------------------------------------------------------
# Chat sessions (2026-08-15) — one entry per conversation (chat_id), letting
# the frontend show a "Chats" list with real status instead of a plain saved-
# archive list, and giving background-completed/paused turns somewhere to
# register as unread. Not the archive itself (still a plain .md in Chats/,
# written by routers/chat.py's _write_chat_archive) — this is the index over
# it: {chat_id, filename, title, status, unread, updated_at, last_message_preview}.
# Workspace-scoped (stored under ws_path, like the Chats/ archives themselves,
# not the workspace-agnostic user_path other agent/*.json files use) — a
# conversation's legs always live in one workspace's own Chats/ folder, so its
# index entry has to live there too, or switching workspace mid-conversation
# would silently point the same chat_id at two different physical files.
_SESSIONS_CAP = 50


def _sessions_path(user_name: str, workspace: str):
    return ws_path(user_name, workspace) / "agent" / "chat_sessions.json"


def load_sessions(user_name: str, workspace: str) -> list[dict]:
    return read_json(_sessions_path(user_name, workspace), default={"sessions": []})["sessions"]


def get_session(user_name: str, workspace: str, chat_id: str) -> dict | None:
    return next((s for s in load_sessions(user_name, workspace) if s["chat_id"] == chat_id), None)


def upsert_session(user_name: str, workspace: str, chat_id: str, **fields) -> dict:
    """Create or update one session entry, moving it to the front (most-
    recently-touched-first, same ordering convention as _save_run's runs.json)."""
    path = _sessions_path(user_name, workspace)
    data = read_json(path, default={"sessions": []})
    sessions = data["sessions"]
    existing = next((s for s in sessions if s["chat_id"] == chat_id), None)
    if existing:
        sessions.remove(existing)
        existing.update(fields)
        entry = existing
    else:
        entry = {"chat_id": chat_id, **fields}
    sessions.insert(0, entry)
    data["sessions"] = sessions[:_SESSIONS_CAP]
    write_json(path, data)
    return entry


def mark_session_read(user_name: str, workspace: str, chat_id: str) -> bool:
    path = _sessions_path(user_name, workspace)
    data = read_json(path, default={"sessions": []})
    entry = next((s for s in data["sessions"] if s["chat_id"] == chat_id), None)
    if not entry:
        return False
    entry["unread"] = False
    write_json(path, data)
    return True


def delete_session_by_filename(user_name: str, workspace: str, filename: str) -> None:
    """Called when a saved chat archive is deleted, so its session entry
    (and the now-dangling filename it points at) doesn't linger."""
    path = _sessions_path(user_name, workspace)
    data = read_json(path, default={"sessions": []})
    data["sessions"] = [s for s in data["sessions"] if s.get("filename") != filename]
    write_json(path, data)


# ---------------------------------------------------------------------------
# Chat presence (2026-08-15) — lets routers/chat.py skip a completion/
# approval notification when the requesting user is still actively looking
# at that exact conversation (owner ask: "ai chat only needs to send a
# notification... when the user is not on that module"). POST /chat is a
# synchronous request with no live channel back to the server once it's
# fired, so the server has no way to know "is the tab still open on this
# chat" on its own — Chat.jsx pings this on mount/switch and on an interval
# while the tab is open and visible, so it goes stale on its own once the
# user backgrounds the tab or navigates away, without needing an explicit
# "I left" signal. Deliberately a single most-recent value per user, not
# per-chat_id history — a user only ever actively looks at one conversation
# in one tab at a time; a second open tab just overwrites it with whichever
# ping lands last, an acceptable approximation for a notification nicety.
# Not workspace-scoped, like pending_turns.json — chat_id alone identifies
# the conversation regardless of workspace.
_PRESENCE_STALE_AFTER_SECONDS = 45


def _presence_path(user_name: str):
    return user_path(user_name) / "agent" / "chat_presence.json"


def record_chat_presence(user_name: str, chat_id: str) -> None:
    write_json(
        _presence_path(user_name),
        {"chat_id": chat_id, "seen_at": datetime.now(timezone.utc).isoformat()},
    )


def is_chat_present(user_name: str, chat_id: str) -> bool:
    """True if the user pinged presence for this exact chat_id recently
    enough to assume they're still looking at it right now."""
    data = read_json(_presence_path(user_name), default={})
    if data.get("chat_id") != chat_id or not data.get("seen_at"):
        return False
    try:
        seen_at = datetime.fromisoformat(data["seen_at"])
    except ValueError:
        return False
    age = (datetime.now(timezone.utc) - seen_at).total_seconds()
    return age <= _PRESENCE_STALE_AFTER_SECONDS
