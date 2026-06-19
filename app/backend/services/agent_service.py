"""Agent loop — wraps tool-enabled AI completions over user data."""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from services import task_service, priority_service, journal_service
from services.ai_provider import agent_completion
from services.file_service import (
    user_path,
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
                "title":      {"type": "string"},
                "category":   {"type": "string"},
                "priority":   {"type": "string", "enum": ["High", "Medium", "Low"]},
                "due_date":   {"type": "string"},
                "notes":      {"type": "string"},
                "created_by": {"type": "string", "description": "Name of the assigning user"},
            },
            "required": ["title", "category"],
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
