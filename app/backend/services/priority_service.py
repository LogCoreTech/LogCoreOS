"""Task scoring logic — implements the life priority scoring formula."""
from datetime import date, timedelta
from typing import Any

from services.file_service import (
    parse_priority_order,
    read_json,
    tasks_path,
    override_path,
)


def get_priority_order(user_name: str) -> list[str]:
    """Return active priority order: daily override if today, else profile order."""
    today = date.today().isoformat()
    op = override_path(user_name)
    if op.exists():
        override = read_json(op)
        if override.get("date") == today:
            return override.get("order", [])
    return parse_priority_order(user_name)


def score_task(task: dict, category_order: list[str]) -> int:
    total = len(category_order)
    try:
        cat_idx = category_order.index(task.get("category", ""))
        cat_weight = total - cat_idx
    except ValueError:
        cat_weight = 0  # unknown category gets lowest weight

    priority_weights = {"High": 3, "Medium": 2, "Low": 1}
    pri_weight = priority_weights.get(task.get("priority", "Low"), 1)

    today = date.today()
    urgency = 0
    due = task.get("due_date")
    if due:
        due_date = date.fromisoformat(due)
        if due_date < today:
            urgency = 10
        elif due_date == today:
            urgency = 5
        elif due_date <= today + timedelta(days=7):
            urgency = 2

    return (cat_weight * pri_weight) + urgency


def get_top3(user_name: str) -> list[dict[str, Any]]:
    """Return top 3 scored pending tasks with score attached."""
    tasks_data = read_json(tasks_path(user_name))
    order = get_priority_order(user_name)
    pending = [t for t in tasks_data.get("tasks", []) if t.get("status") == "pending"]
    scored = sorted(pending, key=lambda t: score_task(t, order), reverse=True)
    for task in scored:
        task["_score"] = score_task(task, order)
    return scored[:3]


def get_all_scored(user_name: str) -> list[dict[str, Any]]:
    """Return all pending tasks sorted by score descending."""
    tasks_data = read_json(tasks_path(user_name))
    order = get_priority_order(user_name)
    pending = [t for t in tasks_data.get("tasks", []) if t.get("status") == "pending"]
    for t in pending:
        t["_score"] = score_task(t, order)
    return sorted(pending, key=lambda t: t["_score"], reverse=True)
