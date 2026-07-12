"""Task scoring logic — implements the life priority scoring formula."""

from datetime import timedelta
from typing import Any

from services.auth_service import today_for_user
from services.file_service import read_json, tasks_path
from services.profile_service import get_priority_order


def score_task(task: dict, category_order: list[str], today_str: str) -> int:
    total = len(category_order)
    try:
        cat_idx = category_order.index(task.get("category", ""))
        cat_weight = total - cat_idx
    except ValueError:
        cat_weight = 0

    priority_weights = {"High": 3, "Medium": 2, "Low": 1}
    pri_weight = priority_weights.get(task.get("priority", "Low"), 1)

    urgency = 0
    due = task.get("due_date")
    if due:
        from datetime import date

        today = date.fromisoformat(today_str)
        due_date = date.fromisoformat(due)
        if due_date < today:
            urgency = 10
        elif due_date == today:
            urgency = 5
        elif due_date <= today + timedelta(days=7):
            urgency = 2

    return (cat_weight * pri_weight) + urgency


def _pending_non_goal(tasks: list[dict]) -> list[dict]:
    # Goal-type tasks live in the Goals module (and goal_drift suggestions) —
    # they don't compete in daily task scoring, top3, or the morning digest.
    return [t for t in tasks if t.get("status") == "pending" and t.get("type") != "goal"]


def get_top3(user_name: str, workspace: str = "personal") -> list[dict[str, Any]]:
    """Return top 3 scored pending tasks with score attached."""
    tasks_data = read_json(tasks_path(user_name, workspace), default={"tasks": []})
    order = get_priority_order(user_name, workspace)
    today_str = today_for_user(user_name).isoformat()
    pending = _pending_non_goal(tasks_data.get("tasks", []))
    for task in pending:
        task["_score"] = score_task(task, order, today_str)
    return sorted(pending, key=lambda t: t["_score"], reverse=True)[:3]


def get_all_scored(user_name: str, workspace: str = "personal") -> list[dict[str, Any]]:
    """Return all pending tasks sorted by score descending."""
    tasks_data = read_json(tasks_path(user_name, workspace), default={"tasks": []})
    order = get_priority_order(user_name, workspace)
    today_str = today_for_user(user_name).isoformat()
    pending = _pending_non_goal(tasks_data.get("tasks", []))
    for t in pending:
        t["_score"] = score_task(t, order, today_str)
    return sorted(pending, key=lambda t: t["_score"], reverse=True)
