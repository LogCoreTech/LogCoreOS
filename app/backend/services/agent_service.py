"""Agent loop — wraps tool-enabled AI completions over user data."""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from services import task_service, priority_service, journal_service, notes_service
from services import profile_service, push_service, auth_service
from services.ai_provider import agent_completion
from services.file_service import (
    user_path,
    brain_path,
    read_json,
    write_json,
    read_markdown,
    write_markdown,
    resolve_user_md_path,
)

MAX_STEPS = 10
_RUNS_CAP = 50
_BRAIN_SKIP = {"Tasks"}

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
                "title":      {"type": "string", "description": "Task title"},
                "category":   {"type": "string", "description": "Category (e.g. Health, Work, Personal)"},
                "priority":   {"type": "string", "enum": ["High", "Medium", "Low"]},
                "type":       {"type": "string", "enum": ["todo", "recurring", "goal", "appointment"]},
                "recurrence": {"type": "string", "enum": ["daily", "weekly", "monthly"]},
                "due_date":   {"type": "string", "description": "Due date YYYY-MM-DD"},
                "due_time":   {"type": "string", "description": "Due time HH:MM (requires due_date)"},
                "notes":      {"type": "string"},
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
                "task_id":  {"type": "string", "description": "Task ID to update"},
                "title":    {"type": "string"},
                "category": {"type": "string"},
                "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "status":   {"type": "string", "enum": ["pending", "done", "skipped"]},
                "due_date": {"type": "string"},
                "due_time": {"type": "string"},
                "notes":    {"type": "string"},
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
                "path":    {"type": "string", "description": "Relative path to an existing .md file"},
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
                "path":    {"type": "string", "description": "Relative path for the new .md file, e.g. 'Notes/MyNote.md'"},
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
                "date":    {"type": "string", "description": "Date in YYYY-MM-DD format"},
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
                "path":    {"type": "string", "description": "Relative note path, e.g. 'Work/Meeting Notes'"},
                "content": {"type": "string", "description": "Initial markdown content (defaults to empty)"},
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
                "path":    {"type": "string", "description": "Relative note path, e.g. 'Work/Meeting Notes'"},
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
                "path": {"type": "string", "description": "Relative note path, e.g. 'Work/Meeting Notes'"},
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
                    "description": "Dict of profile fields to update, e.g. {\"big_goal\": \"Run a marathon\", \"occupation\": \"Engineer\"}",
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
                "target":  {"type": "string", "enum": ["short", "long"], "description": "Which memory file to append to (default: short)"},
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
                "content": {"type": "string", "description": "Full new markdown content for the memory file"},
                "target":  {"type": "string", "enum": ["short", "long"], "description": "Which memory file to rewrite (default: short)"},
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
                "limit":      {"type": "integer", "description": "Max number of tasks to return (default 20)"},
                "since_date": {"type": "string", "description": "Only return tasks completed on or after this date (YYYY-MM-DD)"},
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
                "to_path":   {"type": "string", "description": "New note path, e.g. 'Brainstorms/Ideas'"},
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
                "path": {"type": "string", "description": "Folder path relative to Notes/, e.g. 'Projects' or 'Projects/Work'"},
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
                            "title":      {"type": "string"},
                            "category":   {"type": "string"},
                            "priority":   {"type": "string", "enum": ["High", "Medium", "Low"]},
                            "type":       {"type": "string", "enum": ["todo", "recurring", "goal", "appointment"]},
                            "due_date":   {"type": "string"},
                            "due_time":   {"type": "string"},
                            "notes":      {"type": "string"},
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
                "body":  {"type": "string", "description": "Notification body text"},
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
                "task_id": {"type": "string", "description": "ID of the shared task to mark complete"},
            },
            "required": ["task_id"],
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
                "title":       {"type": "string"},
                "category":    {"type": "string"},
                "priority":    {"type": "string", "enum": ["High", "Medium", "Low"]},
                "due_date":    {"type": "string"},
                "notes":       {"type": "string"},
                "assigned_to": {"type": "string", "description": "Username of the member responsible for this task"},
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
                "task_id":     {"type": "string", "description": "Task ID to update"},
                "title":       {"type": "string"},
                "category":    {"type": "string"},
                "priority":    {"type": "string", "enum": ["High", "Medium", "Low"]},
                "due_date":    {"type": "string"},
                "due_time":    {"type": "string"},
                "notes":       {"type": "string"},
                "assigned_to": {"type": "string", "description": "Reassign to a different member"},
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
]


def _get_tools(user: dict) -> list[dict]:
    tools = list(_USER_TOOLS)
    if user.get("role") == "admin":
        tools.extend(_ADMIN_TOOLS)
    return tools


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def _execute_tool(name: str, inputs: dict, user: dict) -> Any:
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
                base = user_path(user["name"])
                if not base.exists():
                    return []
                files = []
                for p in sorted(base.rglob("*.md")):
                    rel = p.relative_to(base)
                    if not any(part in _BRAIN_SKIP for part in rel.parts):
                        files.append({"path": str(rel), "name": p.name})
                return files

            case "read_brain_file":
                path = resolve_user_md_path(user["name"], inputs["path"])
                if not path.exists():
                    return {"error": f"File not found: {inputs['path']!r}"}
                return read_markdown(path)

            case "write_brain_file":
                path = resolve_user_md_path(user["name"], inputs["path"])
                if not path.exists():
                    return {"error": f"File not found: {inputs['path']!r}. Use create_brain_file for new files."}
                write_markdown(path, inputs["content"])
                return {"ok": True}

            case "create_brain_file":
                path = resolve_user_md_path(user["name"], inputs["path"])
                if path.exists():
                    return {"error": f"File already exists: {inputs['path']!r}. Use write_brain_file to edit it."}
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
                return notes_service.create_note(user["name"], inputs["path"], inputs.get("content", ""))

            case "update_note":
                result = notes_service.update_note(user["name"], inputs["path"], inputs["content"])
                if result is None:
                    return {"error": f"Note not found: {inputs['path']!r}. Use create_note to make a new one."}
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
                mem_path = user_path(user["name"]) / fname
                today = date.today().isoformat()
                existing = mem_path.read_text() if mem_path.exists() else ""
                safe_content = inputs["content"].replace("</brain_data>", "[/brain_data]")
                updated = existing.rstrip() + f"\n\n## {today}\n\n{safe_content}\n"
                write_markdown(mem_path, updated)
                return {"ok": True, "target": fname}

            case "rewrite_memory":
                target = inputs.get("target", "short")
                fname = "Long_Term_Memory.md" if target == "long" else "Short_Term_Memory.md"
                mem_path = user_path(user["name"]) / fname
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
                base = user_path(user["name"])
                results = []
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
                    results.append({"path": str(rel), "snippet": snippet})
                return results

            case "move_note":
                return notes_service.move_item(user["name"], inputs["from_path"], inputs["to_path"], "note")

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

            case "complete_shared_task":
                task = task_service.get_task("_household", inputs["task_id"])
                if task is None:
                    return {"error": f"Shared task {inputs['task_id']!r} not found"}
                if user.get("role") != "admin" and task.get("assigned_to") != user["name"]:
                    return {"error": "Not authorized — you can only complete tasks assigned to you"}
                result = task_service.update_task("_household", inputs["task_id"], {
                    "status": "done",
                    "completed_by": user["name"],
                })
                return result or {"error": "Update failed"}

            case "list_users":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                from services.auth_service import _load_auth
                safe = {"id", "name", "email", "role", "timezone"}
                return [{k: v for k, v in u.items() if k in safe} for u in _load_auth()["users"]]

            case "list_shared_tasks":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                return task_service.list_tasks("_household")

            case "add_shared_task":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                return task_service.add_task("_household", inputs)

            case "update_shared_task":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                task_id = inputs["task_id"]
                updates = {k: v for k, v in inputs.items() if k != "task_id"}
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

            case _:
                return {"error": f"Unknown tool: {name!r}"}

    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Tool error: {exc}"}


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

async def run_agent(user: dict, goal: str, history: list[dict], system: str) -> dict:
    """Run the agent loop and return a run record."""
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    steps: list[dict] = []
    tools_used = False
    final_answer = ""
    status = "completed"
    last_text = ""

    messages = list(history) + [{"role": "user", "content": goal}]
    active_tools = _get_tools(user)

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

            result = _execute_tool(tc.name, tc.input, user)
            step_entry["output"] = result

            result_str = json.dumps(result) if not isinstance(result, str) else result
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result_str,
            })

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
