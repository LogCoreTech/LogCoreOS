"""Trash registry contract for the calendar module — see module_registry.py's
trash_dispatch()/owned_trash_types and services/trash_service.py's module
docstring for the shared per-module contract. Covers Calendar's own events
AND Household/Team pool events, since all three call the same core
events_service.delete_event() with different store_users (see
docs/MEMORY.md's 2026-08-25 entry on why events_service.py stayed core).
Pure JSON-array record — no associated file.
"""

from services.events_service import get_event, list_events
from services.file_service import events_path, write_json

RECORD_TYPES = ["event"]


def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    event = payload or {}
    title = event.get("title") or "Untitled event"
    subtitle = f"Calendar · {event['start_date']}" if event.get("start_date") else "Calendar"
    return title, subtitle


def restore(store_user: str, workspace: str, entry: dict) -> dict:
    event = entry["payload"]
    if get_event(store_user, event["id"], workspace) is not None:
        raise ValueError(
            "An event with this ID already exists — it may have already been restored."
        )

    events = list_events(store_user, workspace)
    events.append(event)
    write_json(events_path(store_user, workspace), {"events": events})
    return event


def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """list_trash_for_user() only ever reads from the caller's own store or
    an enabled pool's store (see trash_service.py), and event visibility has
    no finer per-item permission than that on either surface today — so
    every entry that reaches this point is already visible to `user`."""
    return True
