"""Admin action audit log (2026-09-18, TASKS.md backlog item): a queryable
trail for the sensitive admin actions that previously left none — user
deletion, role changes, and module toggles (both per-user disabled_modules
edits and instance-wide Mod Store install/uninstall — the latter already had
its own write-only installed_modules_history.json via mod_store_service.py;
this is the first thing to actually read it back, merged in below rather than
replacing that file's existing format).

One append-only, capped JSON file at brain/_system/audit_log.json:
{"entries": [{id, at (ISO), actor: {id, name}, action, target, details}]}.
Not per-user, not per-workspace — this is instance-wide admin activity, same
category as installed_modules_history.json.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from services.file_service import brain_path, read_json, update_json

_ENTRIES_CAP = 500


def _path() -> Path:
    return brain_path() / "_system" / "audit_log.json"


def record(actor: dict, action: str, target: str, details: dict | None = None) -> None:
    """Append one entry. `actor` is a user dict (only id/name are kept);
    `action` is a short dotted verb (e.g. "user.delete", "user.role_change");
    `target` is a human-readable description of what was acted on."""
    entry = {
        "id": str(uuid.uuid4()),
        "at": datetime.now(timezone.utc).isoformat(),
        "actor": {"id": actor.get("id"), "name": actor.get("name")},
        "action": action,
        "target": target,
        "details": details or {},
    }

    def _append(data: dict) -> dict:
        entries = data.get("entries", [])
        entries.append(entry)
        data["entries"] = entries[-_ENTRIES_CAP:]
        return data

    update_json(_path(), _append, default={"entries": []})


def list_entries(limit: int = 100) -> list[dict]:
    """Most-recent-first, capped at `limit` (default 100, max 500 — the same
    cap entries are stored under, so a caller can never usefully ask for
    more than actually exists)."""
    limit = max(1, min(limit, _ENTRIES_CAP))
    entries = read_json(_path(), default={"entries": []}).get("entries", [])
    return list(reversed(entries))[:limit]
