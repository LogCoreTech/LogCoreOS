"""Derived share-routing cache for Contacts (mirrors finance_index.py).

Maps owner → workspace → share-target tokens so list_visible_contacts/find_contact
only scan stores that could contain something shared with the viewer. NEVER a
source of truth — rebuildable from Brain files at any time; warmed at startup and
updated incrementally on access writes.
"""

import logging

from services.file_service import brain_path, read_json, write_json

logger = logging.getLogger("logcore.contacts")


def _index_path():
    return brain_path() / "_system" / "contacts_share_index.json"


def _collect_targets(contacts: list[dict]) -> list[str]:
    tokens: set[str] = set()
    for contact in contacts:
        for entry in contact.get("shared_with") or []:
            if entry.get("target"):
                tokens.add(entry["target"])
    return sorted(tokens)


def _scan_owner(owner: str) -> dict:
    from services import contacts_service

    out = {}
    for workspace in ("personal", "business"):
        contacts = contacts_service.list_contacts(owner, workspace)
        tokens = _collect_targets(contacts)
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
    """Full rescan across all real users (pools never share via shared_with)."""
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
    """Owners whose shares could target this viewer in this workspace."""
    data = read_json(_index_path(), default={"owners": {}})
    wanted = {viewer, "household", f"role:{viewer_role}"}
    if workspace == "business":
        wanted.add("team")
    out = []
    for owner, ws_map in (data.get("owners") or {}).items():
        if owner == viewer:
            continue
        tokens = set(ws_map.get(workspace) or [])
        if tokens & wanted:
            out.append(owner)
    return sorted(out)
