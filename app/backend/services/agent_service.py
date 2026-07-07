"""Agent loop — wraps tool-enabled AI completions over user data."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from services import (
    auth_service,
    journal_service,
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

MAX_STEPS = 10
_RUNS_CAP = 50
_BRAIN_SKIP = {"Tasks"}

# Tools available in research mode — read-only access only
_RESEARCH_TOOLS = {
    "list_tasks",
    "get_top3_tasks",
    "get_scored_tasks",
    "list_brain_files",
    "read_brain_file",
    "get_profile",
    "read_journal_entry",
    "list_journal_entries",
    "list_notes",
    "get_task_history",
    "search_brain",
    "get_week_snapshot",
    "search_web",
    # admin read-only
    "list_users",
    "list_household_members",
    "list_shared_tasks",
    "read_system_file",
}

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
        "name": "read_journal_entry",
        "description": "Read the user's journal entry for a specific date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            },
            "required": ["date"],
        },
    },
    {
        "name": "write_journal_entry",
        "description": "Create or update the user's journal entry for a specific date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "content": {"type": "string", "description": "Full markdown content of the entry"},
            },
            "required": ["date", "content"],
        },
    },
    {
        "name": "list_notes",
        "description": "List all notes and folders in the user's Notes brain folder.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "create_note",
        "description": "Create a new note. Path is relative to Notes/ without the .md extension, e.g. 'Work/Meeting Notes' or 'Ideas'.",
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
        "description": "Overwrite an existing note's content. Use list_notes or read_brain_file first if you need to see what's there.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative note path, e.g. 'Work/Meeting Notes'",
                },
                "content": {"type": "string", "description": "New full markdown content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "delete_note",
        "description": "Permanently delete a note by path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative note path, e.g. 'Work/Meeting Notes'",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_profile",
        "description": (
            "Read the user's full profile. Fields include: occupation, city, state, country, pronouns, "
            "wake_weekday, wake_weekend, bedtime, work_hours, height, weight, blood_type, diet, exercise, "
            "conditions, medications, employer, industry, education, years_experience, skills, "
            "marital_status, partner, children (list of {name, age}), pets, income_range, savings_goal, "
            "budget_style, life_mission, big_goal, core_values, key_constraints, communication_style, "
            "tone, response_language, topics_to_emphasize, topics_to_avoid, notes, "
            "priority_order (list of category strings)."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "update_profile",
        "description": (
            "Update one or more profile fields. Pass only the fields you want to change — existing fields "
            "are preserved. Automatically regenerates Profile.md. "
            "Goals and completable items belong in tasks (type='goal'), not here. "
            "This is for biographical/aspirational context: life mission, values, health, family, work, AI preferences."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": 'Dict of profile fields to update, e.g. {"big_goal": "Run a marathon", "occupation": "Engineer"}',
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
        "description": "Search across all the user's Brain markdown files (notes, journal, memory, profile) for a keyword or phrase.",
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
        "description": "Move or rename a note. Paths are relative to Notes/ without .md extension.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_path": {"type": "string", "description": "Current note path, e.g. 'Ideas'"},
                "to_path": {
                    "type": "string",
                    "description": "New note path, e.g. 'Brainstorms/Ideas'",
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
        "name": "get_week_snapshot",
        "description": "Get a full overview of the current week — tasks due this week, overdue tasks, and tasks completed this week. Use at the start of any planning or review session.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_journal_entries",
        "description": "List journal entries with their full content, optionally filtered by date range. Useful for progress summaries and reflection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "since": {
                    "type": "string",
                    "description": "Only return entries on or after this date (YYYY-MM-DD)",
                },
                "until": {
                    "type": "string",
                    "description": "Only return entries on or before this date (YYYY-MM-DD)",
                },
                "limit": {"type": "integer", "description": "Max entries to return (default 7)"},
            },
            "required": [],
        },
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
        "name": "get_home_state",
        "description": (
            "Get the current state of one or more Home Assistant entities (lights, sensors, thermostats, locks, etc.). "
            "Only available when Home Assistant is configured."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of entity_ids, e.g. ['light.living_room', 'sensor.temperature']",
                },
            },
            "required": ["entity_ids"],
        },
    },
    {
        "name": "control_home_device",
        "description": (
            "Control a Home Assistant device. Use domain/service per HA docs "
            "(e.g. light/turn_on, switch/turn_off, climate/set_temperature). "
            "Only available when Home Assistant is configured."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "HA entity_id to control"},
                "domain": {
                    "type": "string",
                    "description": "HA service domain, e.g. 'light', 'switch', 'climate'",
                },
                "service": {
                    "type": "string",
                    "description": "HA service name, e.g. 'turn_on', 'turn_off', 'set_temperature'",
                },
                "data": {
                    "type": "object",
                    "description": "Optional service data, e.g. {brightness_pct: 80, temperature: 72}",
                },
            },
            "required": ["entity_id", "domain", "service"],
        },
    },
    {
        "name": "activate_scene",
        "description": "Activate a Home Assistant scene by its entity_id. Only available when Home Assistant is configured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Scene entity_id, e.g. 'scene.movie_time'",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "trigger_home_automation",
        "description": "Trigger a Home Assistant automation by its entity_id. Only available when Home Assistant is configured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Automation entity_id, e.g. 'automation.morning_routine'",
                },
            },
            "required": ["entity_id"],
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
]


def _get_tools(user: dict) -> list[dict]:
    from services.ha_service import is_configured as _ha_configured

    _HA_TOOL_NAMES = {
        "get_home_state",
        "control_home_device",
        "activate_scene",
        "trigger_home_automation",
    }
    ha_ok = _ha_configured()
    tools = [t for t in _USER_TOOLS if ha_ok or t["name"] not in _HA_TOOL_NAMES]
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
                for p in sorted(base.rglob("*.md")):
                    rel = p.relative_to(base)
                    if not any(part in _BRAIN_SKIP for part in rel.parts):
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

            case "read_journal_entry":
                entry = journal_service.get_entry(user["name"], inputs["date"])
                if entry is None:
                    return {"date": inputs["date"], "content": "", "exists": False}
                return {**entry, "exists": True}

            case "write_journal_entry":
                return journal_service.upsert_entry(user["name"], inputs["date"], inputs["content"])

            case "list_notes":
                return notes_service.list_notes(user["name"])

            case "create_note":
                return notes_service.create_note(
                    user["name"], inputs["path"], inputs.get("content", "")
                )

            case "update_note":
                result = notes_service.update_note(user["name"], inputs["path"], inputs["content"])
                if result is None:
                    return {
                        "error": f"Note not found: {inputs['path']!r}. Use create_note to make a new one."
                    }
                return result

            case "delete_note":
                ok = notes_service.delete_note(user["name"], inputs["path"])
                return {"deleted": ok}

            case "get_profile":
                return profile_service.load_profile(user["name"])

            case "update_profile":
                current = profile_service.load_profile(user["name"])
                current.update(inputs.get("fields", {}))
                return profile_service.save_profile(user["name"], current)

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
                results = []
                for ws_label, base in search_roots:
                    if not base.exists():
                        continue
                    for p in sorted(base.rglob("*.md")):
                        rel = p.relative_to(base)
                        if any(part in _BRAIN_SKIP for part in rel.parts):
                            continue
                        try:
                            text = p.read_text()
                        except OSError:
                            continue
                        idx = text.lower().find(query)
                        if idx == -1:
                            continue
                        start = max(0, idx - 100)
                        end = min(len(text), idx + 200)
                        snippet = text[start:end].strip()
                        path_label = f"{ws_label}/{rel}" if cross_workspace else str(rel)
                        results.append({"path": path_label, "snippet": snippet})
                return results

            case "move_note":
                return notes_service.move_item(
                    user["name"], inputs["from_path"], inputs["to_path"], "note"
                )

            case "create_note_folder":
                return notes_service.create_folder(user["name"], inputs["path"])

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
                return {
                    "status": "proposed",
                    "summary": inputs["summary"],
                    "actions": inputs.get("actions", []),
                }

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

            case "list_journal_entries":
                since = inputs.get("since")
                until = inputs.get("until")
                limit = int(inputs.get("limit", 7))
                entries = journal_service.list_entries(user["name"])
                if since:
                    entries = [e for e in entries if e["date"] >= since]
                if until:
                    entries = [e for e in entries if e["date"] <= until]
                result = []
                for e in entries[:limit]:
                    full = journal_service.get_entry(user["name"], e["date"])
                    if full:
                        result.append({"date": e["date"], "content": full.get("content", "")})
                return result

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

            case "get_home_state":
                from services.ha_service import get_state as _ha_get_state

                return [_ha_get_state(eid) for eid in inputs["entity_ids"]]

            case "control_home_device":
                from services.ha_service import call_service as _ha_call

                data = dict(inputs.get("data") or {})
                data["entity_id"] = inputs["entity_id"]
                return _ha_call(inputs["domain"], inputs["service"], data)

            case "activate_scene":
                from services.ha_service import call_service as _ha_call

                return _ha_call("scene", "turn_on", {"entity_id": inputs["entity_id"]})

            case "trigger_home_automation":
                from services.ha_service import trigger_automation as _ha_trigger

                return _ha_trigger(inputs["entity_id"])

            case _:
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
) -> dict:
    """Run the agent loop and return a run record."""
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    steps: list[dict] = []
    tools_used = False
    final_answer = ""
    status = "completed"
    last_text = ""

    messages = list(history) + [{"role": "user", "content": goal}]
    all_tools = _get_tools(user)
    if mode == "auto":
        active_tools = [t for t in all_tools if t["name"] != "propose_plan"]
    elif mode == "research":
        active_tools = [t for t in all_tools if t["name"] in _RESEARCH_TOOLS]
    else:  # plan (default)
        active_tools = all_tools

    for step_num in range(MAX_STEPS):
        response = await agent_completion(system, messages, active_tools)
        last_text = response.text

        if not response.tool_calls or response.stop_reason != "tool_use":
            final_answer = response.text
            if response.stop_reason == "max_tokens":
                status = "max_steps_reached"
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
        "goal": goal,
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
