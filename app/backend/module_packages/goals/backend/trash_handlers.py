"""Trash registry contract for the goals module — see module_registry.py's
trash_dispatch()/owned_trash_types and services/trash_service.py's module
docstring for the shared per-module contract. A cascade delete_goal() call
writes one trash entry per deleted goal record (see service.py's
delete_goal() docstring) — restoring one back does NOT re-establish
re-parenting/goal_id-clearing side effects that already happened to other
records, only the raw goal record itself. Pure JSON-array record.
"""

from module_packages.goals.backend.service import _by_id, goals_path, list_goals
from services.file_service import update_json

RECORD_TYPES = ["goal"]


def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    goal = payload or {}
    title = goal.get("title") or "Untitled goal"
    return title, "Goals"


def restore(store_user: str, workspace: str, entry: dict) -> dict:
    goal = entry["payload"]
    if _by_id(list_goals(store_user, workspace)).get(goal["id"]) is not None:
        raise ValueError("A goal with this ID already exists — it may have already been restored.")

    def _add(store: dict) -> dict:
        store.setdefault("goals", []).append(goal)
        return store

    update_json(goals_path(store_user, workspace), _add, default={"goals": []})
    return goal


def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """list_trash_for_user() only ever reads from the caller's own store or
    an enabled (admin-only) pool's store (see trash_service.py), and goal
    visibility has no finer per-item permission than that — so every entry
    that reaches this point is already visible to `user`."""
    return True
