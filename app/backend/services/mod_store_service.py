"""Mod Store — catalog of first-party downloadable modules, plus install state.

Two files in brain/_system/:
  installed_modules.json          — current truth: {"installed": {id: {installed_at, installed_by}}}
  installed_modules_history.json  — append-only, capped log of every install/uninstall event

The catalog (content/mod_store_catalog.json) is marketing metadata (name/description/
icon/category/status), shipped with core releases, hand-authored — not user-editable.
The manifest (module_packages/<id>/manifest.py, via module_registry.py) is the
technical contract. get_catalog() merges the two: a catalog entry with no matching
manifest stays "coming_soon"; one whose manifest failed to import/register shows
"error"; everything else reflects live installed/uninstallable state.
"""

import fcntl
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.file_service import brain_path, read_json, write_json

logger = logging.getLogger("logcore.mod_store")

_CONTENT_PATH = Path(__file__).parent.parent / "content" / "mod_store_catalog.json"
_cache: dict[str, Any] | None = None
_EMPTY_CATALOG: dict[str, Any] = {"modules": []}

_HISTORY_CAP = 200


def _load_catalog_file() -> dict[str, Any]:
    """Static catalog content (cached — shipped with the release, not user-editable)."""
    global _cache
    if _cache is None:
        try:
            with open(_CONTENT_PATH) as f:
                _cache = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.exception("mod store catalog failed to load from %s", _CONTENT_PATH)
            _cache = _EMPTY_CATALOG
    return _cache


def _state_path() -> Path:
    return brain_path() / "_system" / "installed_modules.json"


def _history_path() -> Path:
    return brain_path() / "_system" / "installed_modules_history.json"


def _lock_path() -> Path:
    return brain_path() / "_system" / "installed_modules.lock"


def _with_lock(fn):
    """Run fn() while holding the installed_modules lock — same fcntl.flock
    pattern migrations/runner.py already uses, closing the read-modify-write
    race between two near-simultaneous install/uninstall calls."""
    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def get_installed_ids() -> set[str]:
    return set(read_json(_state_path(), default={"installed": {}}).get("installed", {}))


def is_installed(module_id: str) -> bool:
    return module_id in get_installed_ids()


def _append_history(module_id: str, action: str, by: str) -> None:
    data = read_json(_history_path(), default={"events": []})
    events = data.get("events", [])
    events.append(
        {
            "module_id": module_id,
            "action": action,
            "by": by,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    data["events"] = events[-_HISTORY_CAP:]
    write_json(_history_path(), data)


def mark_installed(module_id: str, by: str) -> None:
    def _do() -> None:
        state = read_json(_state_path(), default={"installed": {}})
        installed = state.setdefault("installed", {})
        installed[module_id] = {
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "installed_by": by,
        }
        write_json(_state_path(), state)
        _append_history(module_id, "install", by)

    _with_lock(_do)


def mark_uninstalled(module_id: str, by: str) -> None:
    def _do() -> None:
        state = read_json(_state_path(), default={"installed": {}})
        installed = state.setdefault("installed", {})
        installed.pop(module_id, None)
        write_json(_state_path(), state)
        _append_history(module_id, "uninstall", by)

    _with_lock(_do)


def get_catalog() -> list[dict[str, Any]]:
    """Every catalog entry, merged with live discovery/install state.

    status precedence: an entry whose manifest failed to import/register is
    "error" regardless of what the static catalog says; otherwise a manifest
    that's actually present flips "coming_soon" to "available"; everything
    else keeps the catalog's own authored status.
    """
    from module_registry import discover_manifests

    manifests, errors = discover_manifests()
    installed_ids = get_installed_ids()

    out: list[dict[str, Any]] = []
    for entry in _load_catalog_file().get("modules", []):
        module_id = entry["id"]
        manifest = manifests.get(module_id)
        status = entry.get("status", "coming_soon")
        if module_id in errors:
            status = "error"
        elif manifest is not None and status == "coming_soon":
            status = "available"

        merged = {
            **entry,
            "status": status,
            "installed": module_id in installed_ids,
            "uninstallable": bool(manifest.uninstallable) if manifest else False,
            "version": manifest.version if manifest else entry.get("version"),
            "error": errors.get(module_id),
        }
        out.append(merged)
    return out
