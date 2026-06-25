"""CRUD operations on tasks.json and tasks_history.json."""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from services.auth_service import get_user_timezone, today_for_user
from services.file_service import (
    read_json,
    write_json,
    tasks_path,
    history_path,  # used by list_history
)


def list_tasks(user_name: str) -> list[dict]:
    return read_json(tasks_path(user_name), default={"tasks": []}).get("tasks", [])


def get_task(user_name: str, task_id: str) -> dict | None:
    return next((t for t in list_tasks(user_name) if t["id"] == task_id), None)


def add_task(user_name: str, task_data: dict) -> dict:
    data = read_json(tasks_path(user_name), default={"tasks": []})
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
    # Pass through optional attribution/assignment fields
    for extra in ("created_by", "assigned_to"):
        if extra in task_data:
            task[extra] = task_data[extra]
    data["tasks"].append(task)
    write_json(tasks_path(user_name), data)
    return task


def update_task(user_name: str, task_id: str, updates: dict) -> dict | None:
    data = read_json(tasks_path(user_name), default={"tasks": []})
    tasks = data["tasks"]
    tz = ZoneInfo(get_user_timezone(user_name))

    for i, task in enumerate(tasks):
        if task["id"] != task_id:
            continue

        if updates.get("status") == "done" and task.get("status") != "done":
            updates["completed_at"] = datetime.now(tz).isoformat()
            if task.get("type") == "recurring":
                updates["last_completed_date"] = today_for_user(user_name).isoformat()
                updates["streak_count"] = task.get("streak_count", 0) + 1

        tasks[i] = {**task, **updates}

        write_json(tasks_path(user_name), data)
        return tasks[i]
    return None


def delete_task(user_name: str, task_id: str) -> bool:
    data = read_json(tasks_path(user_name), default={"tasks": []})
    original = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]
    if len(data["tasks"]) == original:
        return False
    write_json(tasks_path(user_name), data)
    return True


def list_history(user_name: str, limit: int = 50, offset: int = 0) -> list[dict]:
    all_tasks = read_json(history_path(user_name), default={"tasks": []}).get("tasks", [])
    # Return most recent first
    return list(reversed(all_tasks))[offset:offset + limit]
