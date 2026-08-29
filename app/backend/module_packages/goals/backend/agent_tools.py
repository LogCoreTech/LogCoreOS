"""AI agent tools owned by the goals module. Deliberately personal-scope
only (mirrors tasks'/notes' own precedent) — pool goal management isn't
exposed to the AI in this pass, same as household's own pool tools stay
separate/admin-scoped rather than folding into a generic module tool set."""

from module_packages.goals.backend import service as goals_service

TOOL_SCHEMAS = [
    {
        "name": "list_goals",
        "description": "List all of the user's goals, including subgoals. Each has an id, title, parent_id (null for root/life goals), category, due_date, and status.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_goal",
        "description": "Get one goal's full detail: its own record, subgoals, linked tasks, and computed progress percent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string", "description": "Goal ID"},
            },
            "required": ["goal_id"],
        },
    },
    {
        "name": "create_goal",
        "description": "Create a new goal, or a subgoal by passing parent_id. No due date is required.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "notes": {"type": "string"},
                "category": {"type": "string", "description": "Life-priority category (e.g. Health, Career)"},
                "parent_id": {"type": "string", "description": "Optional — makes this a subgoal of another goal"},
                "due_date": {"type": "string", "description": "Optional target date YYYY-MM-DD"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_goal",
        "description": "Update an existing goal by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string"},
                "title": {"type": "string"},
                "notes": {"type": "string"},
                "category": {"type": "string"},
                "due_date": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "done"]},
            },
            "required": ["goal_id"],
        },
    },
    {
        "name": "delete_goal",
        "description": "Delete a goal. By default its subgoals are re-parented up (not deleted) and linked tasks are only unlinked, not deleted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string"},
                "cascade": {"type": "boolean", "description": "Delete subgoals too instead of re-parenting them"},
                "delete_linked_tasks": {"type": "boolean", "description": "Delete linked tasks too instead of just unlinking them"},
            },
            "required": ["goal_id"],
        },
    },
    {
        "name": "link_task_to_goal",
        "description": "Link an existing task to a goal, so it shows up under that goal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "goal_id": {"type": "string"},
            },
            "required": ["task_id", "goal_id"],
        },
    },
    {
        "name": "unlink_task_from_goal",
        "description": "Remove a task's link to whatever goal it's currently linked to. The task itself is unaffected.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
]


def execute(name: str, inputs: dict, user: dict, workspace: str = "personal"):
    if name == "list_goals":
        return goals_service.list_goals(user["name"], workspace)

    if name == "get_goal":
        goal = goals_service.get_goal(user["name"], inputs["goal_id"], workspace)
        if goal is None:
            return {"error": f"Goal {inputs['goal_id']!r} not found"}
        progress = goals_service.compute_progress(user["name"], goal, workspace, user)
        return {
            "goal": goal,
            "subgoals": goals_service.get_subgoals(user["name"], inputs["goal_id"], workspace),
            "linked_tasks": goals_service.get_linked_tasks(user["name"], inputs["goal_id"], workspace),
            "progress": progress,
        }

    if name == "create_goal":
        payload = {k: v for k, v in inputs.items()}
        payload["created_by"] = user["name"]
        try:
            return goals_service.create_goal(user["name"], payload, workspace)
        except ValueError as exc:
            return {"error": str(exc)}

    if name == "update_goal":
        goal_id = inputs["goal_id"]
        updates = {k: v for k, v in inputs.items() if k != "goal_id"}
        try:
            result = goals_service.update_goal(user["name"], goal_id, updates, workspace)
        except ValueError as exc:
            return {"error": str(exc)}
        if result is None:
            return {"error": f"Goal {goal_id!r} not found"}
        return result

    if name == "delete_goal":
        result = goals_service.delete_goal(
            user["name"],
            inputs["goal_id"],
            workspace,
            cascade=bool(inputs.get("cascade", False)),
            delete_linked_tasks=bool(inputs.get("delete_linked_tasks", False)),
        )
        if result is None:
            return {"error": f"Goal {inputs['goal_id']!r} not found"}
        return {"deleted": True, **result}

    if name == "link_task_to_goal":
        from services import task_service

        result = task_service.update_task(user["name"], inputs["task_id"], {"goal_id": inputs["goal_id"]}, workspace)
        if result is None:
            return {"error": f"Task {inputs['task_id']!r} not found"}
        return result

    if name == "unlink_task_from_goal":
        from services import task_service

        result = task_service.update_task(user["name"], inputs["task_id"], {"goal_id": None}, workspace)
        if result is None:
            return {"error": f"Task {inputs['task_id']!r} not found"}
        return result

    return None
