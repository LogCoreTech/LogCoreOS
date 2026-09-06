"""Soft-delete / trash bin — the shared core primitive every module's delete
path routes through, instead of hard-deleting. Trash entries live in a new
Trash/ Brain path per store (personal, Business, and the _household/_team
pools), excluded from AI Brain access exactly like Tasks/Dashboards/Assets/
Contacts/Finance/Goals already are (see agent_service.py's _brain_skip() and
routers/brain.py's _ALWAYS_SKIP).

This module never imports any module_packages/* directly and never inspects
a trash entry's `payload` shape — it only ever dispatches through
module_registry.trash_dispatch(), the same generic-registry pattern
dashboard_blocks/registry.py already uses for block types. See
module_packages/tasks/backend/trash_handlers.py for a worked example of the
per-module side of that contract.

KNOWN LIMITATION: soft_delete() writes the Trash index entry BEFORE moving
any file/directory, and each module's own delete_* function only removes the
item from its live collection AFTER soft_delete() returns successfully. A
crash between those steps leaves a harmless duplicate (still live AND
already in Trash) rather than silently losing the record — but there is no
real cross-file transaction in this flat-file design, so that duplicate
window is a real, accepted residual risk, not something this module
eliminates.
"""

import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.file_service import read_json, update_json, ws_path

logger = logging.getLogger("logcore.trash")

RETENTION_DAYS = 30


class TrashModuleUnavailable(RuntimeError):
    """Raised by restore() when the entry's owning module can't be resolved
    today (never installed, uninstalled, or its manifest/trash_handlers
    failed to import). Callers (routers/trash.py) catch this specifically
    and return a real, readable error — never a bare 404/500."""


def _trash_json_path(store_user: str, workspace: str) -> Path:
    return ws_path(store_user, workspace) / "Trash" / "trash.json"


def _trash_files_dir(store_user: str, workspace: str) -> Path:
    return ws_path(store_user, workspace) / "Trash" / "files"


def soft_delete(
    *,
    store_user: str,
    workspace: str,
    module: str,
    record_type: str,
    original_id: str,
    payload: dict | None,
    deleted_by: str,
    title: str,
    subtitle: str = "",
    original_location: dict | None = None,
    move_path: Path | None = None,
) -> dict:
    """Write a new trash entry, then (if move_path is given) physically
    relocate that file/directory into Trash/files/{entry_id}/. The caller —
    a module's own delete_* function — must only remove the item from its
    own live collection AFTER this returns successfully; see the module
    docstring's KNOWN LIMITATION note for why that ordering matters."""
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    entry: dict[str, Any] = {
        "id": entry_id,
        "module": module,
        "record_type": record_type,
        "original_id": original_id,
        "original_location": original_location or {},
        "store_user": store_user,
        "workspace": workspace,
        "deleted_at": now.isoformat(),
        "deleted_by": deleted_by or store_user,
        "expires_at": (now + timedelta(days=RETENTION_DAYS)).isoformat(),
        "title": title,
        "subtitle": subtitle,
        "payload": payload,
        "file_ref": None,
    }

    def _append(data: dict) -> dict:
        data.setdefault("entries", []).append(entry)
        return data

    update_json(_trash_json_path(store_user, workspace), _append, default={"entries": []})

    if move_path is not None and move_path.exists():
        dest_dir = _trash_files_dir(store_user, workspace) / entry_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / move_path.name
        move_path.rename(dest)  # same-filesystem, atomic
        file_ref = str(dest.relative_to(ws_path(store_user, workspace)))
        entry["file_ref"] = file_ref

        def _set_file_ref(data: dict) -> dict:
            for e in data.get("entries", []):
                if e["id"] == entry_id:
                    e["file_ref"] = file_ref
            return data

        update_json(_trash_json_path(store_user, workspace), _set_file_ref, default={"entries": []})

    return entry


def restore(*, store_user: str, workspace: str, entry_id: str, actor: str) -> dict:
    """Look up the entry, dispatch to its owning module's trash_handlers.restore(),
    then remove the trash entry only on success. Raises TrashModuleUnavailable if
    the module can't be resolved today, or ValueError (propagated from the
    module's own restore()) on a restore-time conflict — both are real,
    user-facing failures the router must surface, never swallow."""
    from module_registry import discover_manifests, trash_dispatch

    trash_path = _trash_json_path(store_user, workspace)
    data = read_json(trash_path, default={"entries": []})
    entry = next((e for e in data.get("entries", []) if e["id"] == entry_id), None)
    if entry is None:
        raise ValueError("Trash entry not found")

    dispatched = trash_dispatch().get(entry["record_type"])
    if dispatched is None:
        manifests, _errors = discover_manifests()
        manifest = manifests.get(entry["module"])
        name = manifest.display_name if manifest else entry["module"]
        raise TrashModuleUnavailable(
            f"{name} is not currently installed — reinstall it from the Mod Store, then try restoring again."
        )

    _module_id, handlers = dispatched
    result = handlers.restore(store_user, workspace, entry)

    def _remove(data: dict) -> dict:
        data["entries"] = [e for e in data.get("entries", []) if e["id"] != entry_id]
        return data

    update_json(trash_path, _remove, default={"entries": []})
    return result


def purge_one(*, store_user: str, workspace: str, entry_id: str) -> bool:
    """Permanently delete one trash entry immediately, ahead of the 30-day
    window — the Trash page's own "delete permanently" action."""
    trash_path = _trash_json_path(store_user, workspace)
    removed = {"ok": False}

    def _remove(data: dict) -> dict:
        entries = data.get("entries", [])
        kept = [e for e in entries if e["id"] != entry_id]
        removed["ok"] = len(kept) != len(entries)
        data["entries"] = kept
        return data

    update_json(trash_path, _remove, default={"entries": []})
    if removed["ok"]:
        file_dir = _trash_files_dir(store_user, workspace) / entry_id
        if file_dir.exists():
            shutil.rmtree(file_dir, ignore_errors=True)
    return removed["ok"]


def purge_expired() -> dict[str, int]:
    """Sweep every user's personal + Business Trash, plus the _household/_team
    pool Trashes, permanently removing any entry past its expires_at — both
    the index entry and, if file_ref is set, its Trash/files/{entry_id}/
    directory. Returns per-store purge counts, logged by the caller the same
    way job_recurring_processor already logs process_all_users()'s result."""
    from services.auth_service import list_users

    now_iso = datetime.now(timezone.utc).isoformat()
    stores: list[tuple[str, str]] = []
    for u in list_users():
        stores.append((u["name"], "personal"))
        stores.append((u["name"], "business"))
    stores.append(("_household", "personal"))
    stores.append(("_team", "personal"))

    results: dict[str, int] = {}
    for store_user, workspace in stores:
        trash_path = _trash_json_path(store_user, workspace)
        if not trash_path.exists():
            continue
        purged_ids: list[str] = []

        def _sweep(data: dict, _purged_ids=purged_ids) -> dict:
            keep = []
            for e in data.get("entries", []):
                if e.get("expires_at", "") <= now_iso:
                    _purged_ids.append(e["id"])
                else:
                    keep.append(e)
            data["entries"] = keep
            return data

        update_json(trash_path, _sweep, default={"entries": []})
        for entry_id in purged_ids:
            file_dir = _trash_files_dir(store_user, workspace) / entry_id
            if file_dir.exists():
                shutil.rmtree(file_dir, ignore_errors=True)
        if purged_ids:
            results[f"{store_user}/{workspace}"] = len(purged_ids)
    return results


def allowed_stores_for(user: dict, workspace: str) -> list[tuple[str, str]]:
    """(store_user, store_workspace) pairs `user` may act on in `workspace` —
    their own store, plus the household/team pool if that module is enabled
    AND `user` is an admin. Shared by list_trash_for_user() below AND
    routers/trash.py's restore/purge/bulk handlers, which MUST check a
    caller-supplied store_user against this before touching that store —
    without this check a caller could pass an arbitrary store_user and
    restore/purge another user's trash entries directly.

    Pool trash is admin-only by design (2026-09-05, owner ask: "split the
    trash bin into two tabs depending on permissions... admins have a
    personal and household/team tabs and non admins only see their own
    items") — deliberately gated on role=="admin" alone, not the finer
    per-pool `pool_edit` grant other household/team mutations use, since
    reviewing/restoring another member's deleted history is a different,
    more sensitive concern than day-to-day pool editing."""
    from services import contacts_service

    disabled = set(user.get("disabled_modules", []))
    stores: list[tuple[str, str]] = [(user["name"], workspace)]
    pool_module = "household" if workspace == "personal" else "team"
    if user.get("role") == "admin" and pool_module not in disabled:
        stores.append((contacts_service.pool_for(workspace), "personal"))
    return stores


def list_trash_for_user(user: dict, workspace: str) -> list[dict]:
    """Every trash entry `user` may see in `workspace` — their own store, plus
    (admins only — see allowed_stores_for()'s docstring) the household pool
    (personal workspace) or team pool (business workspace) if that pool
    module is enabled — filtered per-item through the owning module's own
    access_check(), never a flat union. `disabled_modules` is read straight
    off `user`, already resolved for this request's ambient workspace by
    get_current_user() (routers/auth.py), the same convention
    agent_service.py's _brain_skip() relies on. Each returned entry carries
    a `scope` of "personal" or "pool" (derived from which store it came
    from, not stored in trash.json itself) so the frontend can split Trash
    into tabs without re-deriving pool membership itself. Sorted deleted_at
    desc."""
    from module_registry import trash_dispatch
    from services import contacts_service

    dispatch = trash_dispatch()
    stores = allowed_stores_for(user, workspace)
    pool_users = {contacts_service.POOL_HOUSEHOLD, contacts_service.POOL_TEAM}

    results: list[dict] = []
    for store_user, store_ws in stores:
        data = read_json(_trash_json_path(store_user, store_ws), default={"entries": []})
        scope = "pool" if store_user in pool_users else "personal"
        for entry in data.get("entries", []):
            dispatched = dispatch.get(entry["record_type"])
            if dispatched is None:
                continue
            _module_id, handlers = dispatched
            try:
                if not handlers.access_check(user, workspace, entry):
                    continue
            except Exception:
                logger.exception(
                    "trash access_check failed for %s/%s entry %s",
                    store_user,
                    store_ws,
                    entry.get("id"),
                )
                continue
            results.append({**entry, "scope": scope})

    results.sort(key=lambda e: e.get("deleted_at", ""), reverse=True)
    return results
