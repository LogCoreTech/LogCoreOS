"""Trash registry contract for the tasks module — see module_registry.py's
trash_dispatch()/owned_trash_types and services/trash_service.py's module
docstring for the shared per-module contract (describe/restore/access_check)
every module's own trash_handlers.py implements. Tasks is a pure JSON-array
record with no associated file, so restore() is a plain re-insert.
"""

from services.file_service import tasks_path, update_json
from services.task_service import get_task

RECORD_TYPES = ["task"]


def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    task = payload or {}
    title = task.get("title") or "Untitled task"
    subtitle = f"Tasks · {task['category']}" if task.get("category") else "Tasks"
    return title, subtitle


def restore(store_user: str, workspace: str, entry: dict) -> dict:
    task = entry["payload"]
    if get_task(store_user, task["id"], workspace) is not None:
        raise ValueError("A task with this ID already exists — it may have already been restored.")

    def _add(data: dict) -> dict:
        data.setdefault("tasks", []).append(task)
        return data

    update_json(tasks_path(store_user, workspace), _add, default={"tasks": []})
    return task


def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """list_trash_for_user() only ever reads from the caller's own store or
    an enabled pool's store (see trash_service.py), and task visibility has
    no finer per-item permission than that on either surface today — so
    every entry that reaches this point is already visible to `user`."""
    return True
