"""Trash registry contract for the assets module — see module_registry.py's
trash_dispatch()/owned_trash_types and services/trash_service.py's module
docstring for the shared per-module contract. Sub-records (comments,
attachments, templates) deliberately stay hard-deleted (2026-09-05 owner
decision — no independent restore UX, access fully inherited from the
parent asset) — only the top-level asset record itself is trashable.
"""

from services import assets_index
from services.assets_service import _by_id, _load, _save
from services.file_service import assets_files_path, ws_path

RECORD_TYPES = ["asset"]


def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    asset = payload or {}
    title = asset.get("name") or "Untitled asset"
    return title, "Assets"


def restore(store_user: str, workspace: str, entry: dict) -> dict:
    asset = dict(entry["payload"])
    store = _load(store_user, workspace)
    if _by_id(store["assets"]).get(asset["id"]) is not None:
        raise ValueError(
            "An asset with this ID already exists — it may have already been restored."
        )

    warning = None
    parent_id = asset.get("parent_id")
    if parent_id and _by_id(store["assets"]).get(parent_id) is None:
        # Stale-reference tolerance, same convention Tasks already uses when a
        # linked Goal disappears — clear the reference and restore top-level
        # rather than hard-failing the whole restore.
        asset["parent_id"] = None
        warning = "The original parent asset no longer exists — restored as a top-level asset."

    file_ref = entry.get("file_ref")
    if file_ref:
        src = ws_path(store_user, workspace) / file_ref
        dest = assets_files_path(store_user, workspace) / asset["id"]
        if src.exists() and not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)

    store["assets"].append(asset)
    _save(store_user, workspace, store)
    assets_index.reindex_owner(store_user, workspace)

    return {**asset, "_warning": warning} if warning else asset


def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """list_trash_for_user() only ever reads from the caller's own store or
    an enabled (admin-only) pool's store, and pool asset deletion is already
    admin-only (see the router's own can_delete gate) — so every entry that
    reaches this point is already something `user` is entitled to see."""
    return True
