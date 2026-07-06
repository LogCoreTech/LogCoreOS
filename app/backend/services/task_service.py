"""CRUD operations on tasks.json and tasks_history.json."""

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.auth_service import get_user_timezone, today_for_user
from services.file_service import history_path, read_json, tasks_path, write_json


def list_tasks(user_name: str, workspace: str = "personal") -> list[dict]:
    return read_json(tasks_path(user_name, workspace), default={"tasks": []}).get("tasks", [])


def get_task(user_name: str, task_id: str, workspace: str = "personal") -> dict | None:
    return next((t for t in list_tasks(user_name, workspace) if t["id"] == task_id), None)


def add_task(user_name: str, task_data: dict, workspace: str = "personal") -> dict:
    data = read_json(tasks_path(user_name, workspace), default={"tasks": []})
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
    write_json(tasks_path(user_name, workspace), data)
    return task


def update_task(
    user_name: str, task_id: str, updates: dict, workspace: str = "personal"
) -> dict | None:
    data = read_json(tasks_path(user_name, workspace), default={"tasks": []})
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
        elif updates.get("status") == "pending" and task.get("status") == "done":
            updates["completed_at"] = None
            if task.get("type") == "recurring":
                updates["last_completed_date"] = None
                updates["streak_count"] = max(0, task.get("streak_count", 0) - 1)

        tasks[i] = {**task, **updates}

        write_json(tasks_path(user_name, workspace), data)
        return tasks[i]
    return None


def delete_task(user_name: str, task_id: str, workspace: str = "personal") -> bool:
    data = read_json(tasks_path(user_name, workspace), default={"tasks": []})
    original = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]
    if len(data["tasks"]) == original:
        return False
    write_json(tasks_path(user_name, workspace), data)
    return True


def list_history(
    user_name: str, limit: int = 50, offset: int = 0, workspace: str = "personal"
) -> list[dict]:
    all_tasks = read_json(history_path(user_name, workspace), default={"tasks": []}).get(
        "tasks", []
    )
    return list(reversed(all_tasks))[offset : offset + limit]
