"""App-wide online/offline presence — generalizes agent_service.py's chat-only
presence tracking (record_chat_presence/is_chat_present) to any page, not just
Chat, so a "last seen" signal exists for surfacing an online/offline dot on a
user-linked contact (Item 9, 2026-08-17).

Same shape as chat_presence.json: one small file per user (Layout.jsx pings
this on an interval while the tab is visible, same pattern Chat's own
presence effect already established), so there is no shared-file, multi-
writer concern the way a single presence-for-everyone file would have.
"""

from datetime import datetime, timezone

from services.file_service import read_json, user_path, write_json

_STALE_AFTER_SECONDS = (
    90  # a bit looser than chat's 45s — one ping interval, not tied to a specific view
)


def _presence_path(user_name: str):
    return user_path(user_name) / "presence.json"


def record_presence(user_name: str) -> None:
    write_json(_presence_path(user_name), {"seen_at": datetime.now(timezone.utc).isoformat()})


def is_online(user_name: str) -> bool:
    data = read_json(_presence_path(user_name), default={})
    seen_at = data.get("seen_at")
    if not seen_at:
        return False
    try:
        seen = datetime.fromisoformat(seen_at)
    except ValueError:
        return False
    age = (datetime.now(timezone.utc) - seen).total_seconds()
    return age <= _STALE_AFTER_SECONDS


def last_seen_iso(user_name: str) -> str | None:
    """Raw last-ping timestamp, for a "last seen 5 min / 3 hr / 2 days ago"
    display (owner ask, 2026-08-17) — deliberately returns the ISO string, not
    a pre-formatted label: the frontend already has the viewer's own locale/
    timezone context, and this keeps presence_service from needing to guess
    at display formatting. None if this user has never pinged at all."""
    data = read_json(_presence_path(user_name), default={})
    return data.get("seen_at")
