"""Trash registry contract for the homes module — see module_registry.py's
trash_dispatch()/owned_trash_types and services/trash_service.py's module
docstring for the shared per-module contract. Pure JSON-array record, same
shape as goals'/tasks' own trash_handlers.py.
"""

from module_packages.homes.backend.service import list_homes
from services.file_service import homes_path, update_json

RECORD_TYPES = ["home"]


def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    home = payload or {}
    return home.get("name") or "Untitled home", "Homes"


def restore(store_user: str, workspace: str, entry: dict) -> dict:
    home = entry["payload"]
    if any(h["id"] == home["id"] for h in list_homes(store_user, workspace)):
        raise ValueError("A home with this ID already exists — it may have already been restored.")

    def _add(store: dict) -> dict:
        store.setdefault("homes", []).append(home)
        return store

    update_json(homes_path(store_user, workspace), _add, default={"homes": []})
    return home


def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """list_trash_for_user() only ever reads from the caller's own store or
    an enabled (admin-only) pool's store (see trash_service.py), and a home
    has no finer per-item permission than that — every entry that reaches
    this point is already visible to `user`."""
    return True
