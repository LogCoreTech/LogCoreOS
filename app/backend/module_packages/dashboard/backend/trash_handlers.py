"""Trash registry contract for the dashboard module — see module_registry.py's
trash_dispatch()/owned_trash_types and services/trash_service.py's module
docstring for the shared per-module contract. Only WHOLE-dashboard delete is
trashable — dashboard BLOCK removal deliberately stays out of scope
(2026-09-05 owner decision): no dedicated delete function exists for it
today, both the human UI and the AI's own remove_dashboard_block tool just
save a shorter blocks list via the generic update_dashboard().
"""

from services import dashboard_index
from services.dashboards_service import _load, _save, get_dashboard

RECORD_TYPES = ["dashboard"]


def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    dashboard = payload or {}
    title = dashboard.get("name") or "Untitled dashboard"
    return title, "Dashboards"


def restore(store_user: str, workspace: str, entry: dict) -> dict:
    dashboard = entry["payload"]
    if get_dashboard(store_user, dashboard["id"], workspace) is not None:
        raise ValueError(
            "A dashboard with this ID already exists — it may have already been restored."
        )

    store = _load(store_user, workspace)
    store.setdefault("dashboards", []).append(dashboard)
    _save(store_user, workspace, store)
    dashboard_index.reindex_dashboard(store_user, workspace, dashboard)
    return dashboard


def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """list_trash_for_user() only ever reads from the caller's own store or
    an enabled (admin-only) pool's store, and pool dashboard deletion is
    already gated to the owner or a pool admin (see the router's own
    relation check) — so every entry that reaches this point is already
    something `user` is entitled to see."""
    return True
