"""Pool (household/team) priority order storage.

Real users' profile data lives on their self-contact (services/contacts_service.py)
since the Profile/Contacts merge — this module only still exists for the
`_household`/`_team` pseudo-users, which have no Contact record of their own.
"""

from __future__ import annotations

from pathlib import Path

from services.file_service import read_json, ws_path

DEFAULT_PRIORITY_ORDER = ["Religion", "Family", "Job", "Personal Growth", "Hobbies"]


def _json_path(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "profile.json"


def get_priority_order(user_name: str, workspace: str = "personal") -> list[str]:
    """Priority order for a user or pool. Real users: read from their
    self-contact (the merged source of truth, auto-created if missing).
    Pool pseudo-users (_household/_team): read their own profile.json
    directly — pools have no Contact record."""
    from services import contacts_service

    if contacts_service.is_pool(user_name):
        json_path = _json_path(user_name, workspace)
        if json_path.exists():
            data = read_json(json_path, default={})
            order = data.get("priority_order")
            if order and isinstance(order, list):
                return order
        return list(DEFAULT_PRIORITY_ORDER)

    self_contact = contacts_service.get_self_contact(user_name, create_if_missing=True)
    order = (self_contact.get("priority_order") or {}).get(workspace)
    if order:
        return order
    return list(DEFAULT_PRIORITY_ORDER)
