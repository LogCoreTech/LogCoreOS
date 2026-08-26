"""AI agent tools owned by the household module — TOOL_SCHEMAS is folded into
_get_tools()'s returned list (filtered by disabled_modules first, then by
admin_agent_tool_names() for the 4 admin-only ones below), and execute() is
what agent_service.py's tool executor falls back to for any name its own
core match/case doesn't handle. Returning None means "not one of mine" so
the dispatcher can try the next module.

complete_shared_task is member-accessible (its own admin-or-assignee check
happens inside execute()); the other 4 are listed in the manifest's
admin_agent_tools too, so their schemas are only ever offered to admin
callers in the first place — household is the first converted module to
need that distinction, see module_registry.py's admin_agent_tool_names()."""

from services import auth_service, task_service

TOOL_SCHEMAS = [
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
]


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


def execute(name: str, inputs: dict, user: dict):
    if name == "complete_shared_task":
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

    if name == "list_household_members":
        if user.get("role") != "admin":
            return {"error": "Admin access required"}
        return [{"name": u["name"]} for u in auth_service.list_users()]

    if name == "list_shared_tasks":
        if user.get("role") != "admin":
            return {"error": "Admin access required"}
        return task_service.list_tasks("_household")

    if name == "add_shared_task":
        if user.get("role") != "admin":
            return {"error": "Admin access required"}
        if inputs.get("assigned_to") is not None:
            resolved, err = _resolve_member_name(inputs["assigned_to"])
            if err:
                return {"error": err}
            inputs = {**inputs, "assigned_to": resolved}
        return task_service.add_task("_household", inputs)

    if name == "update_shared_task":
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

    if name == "delete_shared_task":
        if user.get("role") != "admin":
            return {"error": "Admin access required"}
        ok = task_service.delete_task("_household", inputs["task_id"])
        return {"deleted": ok}

    return None
