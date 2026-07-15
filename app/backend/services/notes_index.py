"""Derived share-routing cache for Notes (mirrors contacts_index.py).

Maps owner → workspace → share-target tokens (read from each store's
Notes/_shares.json sidecar) so list_visible_notes only scans stores that could
contain something shared with the viewer. Rebuildable; warmed at startup.
"""

import logging

from services.file_service import brain_path, read_json, write_json

logger = logging.getLogger("logcore.notes")


def _index_path():
    return brain_path() / "_system" / "notes_share_index.json"


def _collect_targets(shares: dict) -> list[str]:
    tokens: set[str] = set()
    for entry in (shares or {}).values():
        for e in entry.get("shared_with") or []:
            if e.get("target"):
                tokens.add(e["target"])
    return sorted(tokens)


def _scan_owner(owner: str) -> dict:
    from services import notes_service

    out = {}
    for workspace in ("personal", "business"):
        tokens = _collect_targets(notes_service.load_shares(owner, workspace))
        if tokens:
            out[workspace] = tokens
    return out


def reindex_owner(owner: str) -> None:
    data = read_json(_index_path(), default={"owners": {}})
    owners = data.setdefault("owners", {})
    entry = _scan_owner(owner)
    if entry:
        owners[owner] = entry
    else:
        owners.pop(owner, None)
    write_json(_index_path(), data)


def rebuild_share_index() -> None:
    users_dir = brain_path() / "USERS"
    owners = {}
    if users_dir.exists():
        for user_dir in users_dir.iterdir():
            if not user_dir.is_dir() or user_dir.name.startswith("_"):
                continue
            entry = _scan_owner(user_dir.name)
            if entry:
                owners[user_dir.name] = entry
    write_json(_index_path(), {"owners": owners})


def sharers_for(viewer: str, viewer_role: str, workspace: str) -> list[str]:
    data = read_json(_index_path(), default={"owners": {}})
    wanted = {viewer, "household", f"role:{viewer_role}"}
    if workspace == "business":
        wanted.add("team")
    out = []
    for owner, ws_map in (data.get("owners") or {}).items():
        if owner == viewer:
            continue
        if set(ws_map.get(workspace) or []) & wanted:
            out.append(owner)
    return sorted(out)
