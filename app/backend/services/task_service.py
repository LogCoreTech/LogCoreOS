"""CRUD operations on tasks.json and tasks_history.json."""

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.auth_service import get_user_timezone, today_for_user
from services.file_service import history_path, read_json, tasks_path, update_json


def list_tasks(user_name: str, workspace: str = "personal") -> list[dict]:
    return read_json(tasks_path(user_name, workspace), default={"tasks": []}).get("tasks", [])


def get_task(user_name: str, task_id: str, workspace: str = "personal") -> dict | None:
    return next((t for t in list_tasks(user_name, workspace) if t["id"] == task_id), None)


def add_task(user_name: str, task_data: dict, workspace: str = "personal") -> dict:
    tz = ZoneInfo(get_user_timezone(user_name))
    task: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "title": task_data["title"],
        "category": task_data.get("category", ""),
        "priority": task_data.get("priority", "Medium"),
        "type": task_data.get("type", "todo"),
        "recurrence": task_data.get("recurrence"),
        "due_date": task_data.get("due_date"),
        "due_time": task_data.get("due_time"),
        "status": "pending",
        "created_at": datetime.now(tz).isoformat(),
        "completed_at": None,
        "notes": task_data.get("notes"),
        "streak_count": 0,
        "last_completed_date": None,
    }
    # Pass through optional attribution/assignment/linking fields
    for extra in ("created_by", "assigned_to", "asset_id"):
        if extra in task_data:
            task[extra] = task_data[extra]

    def _add(data: dict) -> dict:
        data["tasks"].append(task)
        return data

    update_json(tasks_path(user_name, workspace), _add, default={"tasks": []})
    return task


def update_task(
    user_name: str, task_id: str, updates: dict, workspace: str = "personal"
) -> dict | None:
    tz = ZoneInfo(get_user_timezone(user_name))
    found: dict | None = None

    def _update(data: dict) -> dict:
        nonlocal found
        tasks = data["tasks"]
        for i, task in enumerate(tasks):
            if task["id"] != task_id:
                continue

            if updates.get("status") == "done" and task.get("status") != "done":
                updates["completed_at"] = datetime.now(tz).isoformat()
                if task.get("type") == "recurring":
                    updates["last_completed_date"] = today_for_user(user_name).isoformat()
                    updates["streak_count"] = task.get("streak_count", 0) + 1
            elif updates.get("status") == "pending" and task.get("status") == "done":
                updates["completed_at"] = None
                if task.get("type") == "recurring":
                    updates["last_completed_date"] = None
                    updates["streak_count"] = max(0, task.get("streak_count", 0) - 1)

            tasks[i] = {**task, **updates}
            found = tasks[i]
            break
        return data

    update_json(tasks_path(user_name, workspace), _update, default={"tasks": []})
    return found


def delete_task(user_name: str, task_id: str, workspace: str = "personal") -> bool:
    deleted = False

    def _delete(data: dict) -> dict:
        nonlocal deleted
        original = len(data["tasks"])
        data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]
        deleted = len(data["tasks"]) != original
        return data

    update_json(tasks_path(user_name, workspace), _delete, default={"tasks": []})
    return deleted


def cleanup_done_goals(user_name: str, workspace: str = "personal") -> int:
    """Archive all completed goals to history (the Goals 'Clear completed' action).

    Goals are excluded from the nightly sweep, so they accumulate in the Done view
    until the user clears them here. Returns the number archived.
    """
    # Unlocked peek to decide what to archive and as an early-return — the
    # actual removal below re-validates against fresh data under lock, so a
    # concurrent change to one of these exact tasks in between isn't clobbered.
    data = read_json(tasks_path(user_name, workspace), default={"tasks": []})
    to_archive = [t for t in data["tasks"] if t.get("type") == "goal" and t.get("status") == "done"]
    if not to_archive:
        return 0
    archive_ids = {t["id"] for t in to_archive}

    def _append_history(hist: dict) -> dict:
        hist["tasks"].extend(to_archive)
        return hist

    def _remove_archived(data: dict) -> dict:
        still_archivable = {
            t["id"]
            for t in data["tasks"]
            if t["id"] in archive_ids and t.get("type") == "goal" and t.get("status") == "done"
        }
        data["tasks"] = [t for t in data["tasks"] if t["id"] not in still_archivable]
        return data

    # History first, then remove from active — a crash between the two
    # leaves a goal duplicated (recoverable/visible) rather than silently
    # lost, matching the original ordering.
    update_json(history_path(user_name, workspace), _append_history, default={"tasks": []})
    update_json(tasks_path(user_name, workspace), _remove_archived, default={"tasks": []})
    return len(to_archive)


def list_history(
    user_name: str, limit: int = 50, offset: int = 0, workspace: str = "personal"
) -> list[dict]:
    all_tasks = read_json(history_path(user_name, workspace), default={"tasks": []}).get(
        "tasks", []
    )
    return list(reversed(all_tasks))[offset : offset + limit]
