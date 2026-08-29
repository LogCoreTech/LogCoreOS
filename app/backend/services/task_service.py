"""CRUD operations on tasks.json and tasks_history.json."""

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.auth_service import get_user_timezone, today_for_user
from services.file_service import history_path, read_json, tasks_path, update_json

_COMPLETION_LOG_CAP = 90  # comfortably more than the 30-day rate window goals_service reads


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
        "completion_log": [],
        "tags": task_data.get("tags") or [],
    }
    # Pass through optional attribution/assignment/linking fields
    for extra in ("created_by", "assigned_to", "asset_id", "goal_id"):
        if extra in task_data:
            task[extra] = task_data[extra]

    if task_data.get("counts_toward_goal") is not None:
        task["counts_toward_goal"] = task_data["counts_toward_goal"]
    elif task.get("type") == "recurring" and task.get("goal_id"):
        # A recurring task created already-linked to a goal (the "+ Task"
        # flow inside a goal) opts out of the rollup by default — owner
        # chose opt-in (2026-08-29): linking a recurring task shouldn't
        # silently move a goal's percentage until asked to.
        task["counts_toward_goal"] = False

    if task["tags"]:
        from services.tags_service import register_tags

        register_tags(user_name, workspace, task["tags"])

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

            if (
                updates.get("goal_id")
                and updates["goal_id"] != task.get("goal_id")
                and task.get("type") == "recurring"
                and "counts_toward_goal" not in updates
            ):
                # Newly linking a recurring task to a goal — opt-in default
                # (see add_task's own comment for why).
                updates["counts_toward_goal"] = False

            if updates.get("status") == "done" and task.get("status") != "done":
                updates["completed_at"] = datetime.now(tz).isoformat()
                if task.get("type") == "recurring":
                    today_str = today_for_user(user_name).isoformat()
                    updates["last_completed_date"] = today_str
                    updates["streak_count"] = task.get("streak_count", 0) + 1
                    log = [e for e in (task.get("completion_log") or []) if e.get("date") != today_str]
                    log.append({"date": today_str})
                    updates["completion_log"] = log[-_COMPLETION_LOG_CAP:]
            elif updates.get("status") == "pending" and task.get("status") == "done":
                updates["completed_at"] = None
                if task.get("type") == "recurring":
                    updates["last_completed_date"] = None
                    updates["streak_count"] = max(0, task.get("streak_count", 0) - 1)
                    undone_date = (task.get("last_completed_date") or "")
                    updates["completion_log"] = [
                        e for e in (task.get("completion_log") or []) if e.get("date") != undone_date
                    ]

            if updates.get("tags"):
                from services.tags_service import register_tags

                register_tags(user_name, workspace, updates["tags"])

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


def list_history(
    user_name: str, limit: int = 50, offset: int = 0, workspace: str = "personal"
) -> list[dict]:
    all_tasks = read_json(history_path(user_name, workspace), default={"tasks": []}).get(
        "tasks", []
    )
    return list(reversed(all_tasks))[offset : offset + limit]
