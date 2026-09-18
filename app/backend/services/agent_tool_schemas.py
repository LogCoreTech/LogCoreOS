"""Core AI agent tool schemas (Anthropic input_schema format — translated for
OpenAI by ai_provider) — pure tool-name/description/input-schema data, zero
logic. Split out of agent_service.py 2026-09-18 (TASKS.md backlog item) since
every module-owned tool already moved to its own module_packages/*/backend/
agent_tools.py during the Mod Store conversion; what remained here is the
core, non-module-owned tool set every user (or admin) gets regardless of
which modules are installed. Re-exported by agent_service.py so
agent_service._USER_TOOLS/_ADMIN_TOOLS keep resolving unchanged for every
existing caller (tests included)."""

_USER_TOOLS: list[dict] = [
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
        "name": "update_profile",
        "description": (
            "Update one or more profile fields on the user's own Contact record. Pass only the fields you "
            "want to change — existing fields are preserved. "
            "Concrete goals belong in the Goals module (create_goal) and day-to-day to-dos in "
            "Tasks (add_task), not here. "
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
        "name": "send_notification",
        "description": "Send a web push notification to the user's enabled devices.",
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
        "name": "run_suggestion",
        "description": "Immediately trigger a proactive suggestion by ID. Built-in IDs: 'daily_digest', 'overdue_alert', 'weekly_review', 'goal_drift', 'goal_due_urgency'. Custom suggestions use their UUID.",
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
        "description": "Enable/disable a suggestion or change its delivery settings. Built-in IDs: 'daily_digest', 'overdue_alert', 'weekly_review', 'goal_drift', 'goal_due_urgency'. Custom suggestions use their UUID.",
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
]

_ADMIN_TOOLS: list[dict] = [
    {
        "name": "list_users",
        "description": "List all users in the system with basic info (admin only).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
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
