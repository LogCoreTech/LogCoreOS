"""Nightly recurring task processor — advances due dates and manages streaks."""
import calendar
from datetime import timedelta

from services.auth_service import today_for_user
from services.file_service import read_json, write_json, tasks_path, history_path, brain_path


def _next_due(due: str, recurrence: str) -> str:
    from datetime import date
    d = date.fromisoformat(due)
    if recurrence == "daily":
        return (d + timedelta(days=1)).isoformat()
    if recurrence == "weekly":
        return (d + timedelta(weeks=1)).isoformat()
    if recurrence == "monthly":
        month = d.month + 1
        year = d.year + (month > 12)
        month = (month - 1) % 12 + 1
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day).isoformat()
    return (d + timedelta(days=1)).isoformat()


def process_user(user_name: str) -> dict:
    today = today_for_user(user_name).isoformat()
    path = tasks_path(user_name)
    data = read_json(path, default={"tasks": []})
    advanced = 0
    broken = 0

    # Archive done non-recurring tasks completed before today
    tasks_to_archive = []
    for t in data["tasks"]:
        if t.get("type") == "recurring" or t.get("status") != "done":
            continue
        completed_date = (t.get("completed_at") or "")[:10]
        if completed_date and completed_date < today:
            tasks_to_archive.append(t)
    if tasks_to_archive:
        hist = read_json(history_path(user_name), default={"tasks": []})
        hist["tasks"].extend(tasks_to_archive)
        write_json(history_path(user_name), hist)
        archive_ids = {t["id"] for t in tasks_to_archive}
        data["tasks"] = [t for t in data["tasks"] if t["id"] not in archive_ids]

    for task in data["tasks"]:
        if task.get("type") != "recurring":
            continue
        due = task.get("due_date") or today
        recurrence = task.get("recurrence", "daily")

        if task.get("status") == "done" and task.get("last_completed_date") and task.get("last_completed_date") < today:
            task["due_date"] = _next_due(due, recurrence)
            task["status"] = "pending"
            advanced += 1
        elif task.get("status") == "pending" and due < today:
            # Advance to next occurrence so this branch doesn't trigger every night
            task["streak_count"] = 0
            task["due_date"] = _next_due(today, recurrence)
            broken += 1

    write_json(path, data)
    return {"user": user_name, "advanced": advanced, "broken_streaks": broken}


def process_all_users() -> list[dict]:
    users_dir = brain_path() / "USERS"
    results = []
    for user_dir in users_dir.iterdir():
        if user_dir.name.startswith("_") or not user_dir.is_dir():
            continue
        tp = tasks_path(user_dir.name)
        if tp.exists():
            results.append(process_user(user_dir.name))
    return results
