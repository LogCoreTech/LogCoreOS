"""AI agent tools owned by the tasks module — TOOL_SCHEMAS is folded into
_get_tools()'s returned list (filtered by disabled_modules first), and
execute() is what agent_service.py's tool executor falls back to for any
name its own core match/case doesn't handle. Returning None means "not one
of mine" so the dispatcher can try the next module.

Deliberately narrow: only the 9 tools operating on the caller's OWN personal
tasks move here. The 5 household-pool tools (list_shared_tasks,
add_shared_task, update_shared_task, delete_shared_task,
complete_shared_task) stay in agent_service.py's core _USER_TOOLS/
_ADMIN_TOOLS — same reasoning as dashboard_blocks/_pool.py's PoolTasksBlock
staying core, unowned, until Household/Team's own future conversion: they're
conceptually Household's domain, just implemented via task_service against
the "_household" pseudo-user, same as routers/shared.py itself.

All 9 preserve exact pre-conversion behavior: they call task_service/
priority_service with only (user["name"], inputs) — no workspace param —
same as the inline match/case they replace, so they still implicitly default
to the personal workspace regardless of the chat's actual active workspace.
Not a regression introduced by this move; not fixed here either, since
fixing it is out of scope for a pure relocation."""

from services import priority_service, task_service

TOOL_SCHEMAS = [
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
        "name": "get_week_snapshot",
        "description": "Get a full overview of the current week — tasks due this week, overdue tasks, and tasks completed this week. Use at the start of any planning or review session.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def execute(name: str, inputs: dict, user: dict, workspace: str = "personal"):
    # Accepted for signature parity with the generic dispatch (widened
    # 2026-08-26 for notes/'s own workspace-aware tools) but still
    # deliberately unused here — see the module docstring above for why
    # these 9 tools staying implicitly personal-only is a pre-existing,
    # out-of-scope-for-this-move behavior, not something this signature
    # change fixes or regresses.
    if name == "list_tasks":
        return task_service.list_tasks(user["name"])

    if name == "add_task":
        return task_service.add_task(user["name"], inputs)

    if name == "update_task":
        task_id = inputs["task_id"]
        updates = {k: v for k, v in inputs.items() if k != "task_id"}
        result = task_service.update_task(user["name"], task_id, updates)
        if result is None:
            return {"error": f"Task {task_id!r} not found"}
        return result

    if name == "delete_task":
        ok = task_service.delete_task(user["name"], inputs["task_id"])
        return {"deleted": ok}

    if name == "get_top3_tasks":
        return priority_service.get_top3(user["name"])

    if name == "get_scored_tasks":
        return priority_service.get_all_scored(user["name"])

    if name == "get_task_history":
        limit = int(inputs.get("limit", 20))
        since = inputs.get("since_date")
        history = task_service.list_history(user["name"], limit=limit)
        if since:
            history = [t for t in history if (t.get("completed_at") or "") >= since]
        return history

    if name == "create_tasks":
        created = []
        for t in inputs.get("tasks", []):
            created.append(task_service.add_task(user["name"], t))
        return created

    if name == "get_week_snapshot":
        from datetime import timedelta

        from services.auth_service import today_for_user

        today = today_for_user(user["name"])
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        ws, we, ts = week_start.isoformat(), week_end.isoformat(), today.isoformat()
        all_tasks = task_service.list_tasks(user["name"])
        completed = task_service.list_history(user["name"], limit=50)
        return {
            "week_start": ws,
            "week_end": we,
            "due_this_week": [t for t in all_tasks if ws <= (t.get("due_date") or "") <= we],
            "overdue": [t for t in all_tasks if t.get("due_date") and t["due_date"] < ts],
            "no_date": [t for t in all_tasks if not t.get("due_date")],
            "completed_this_week": [
                t for t in completed if ws <= (t.get("completed_at") or "")[:10] <= we
            ],
        }

    return None
