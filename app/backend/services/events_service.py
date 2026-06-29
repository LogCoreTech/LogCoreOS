"""CRUD operations on Calendar/events.json."""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from services.auth_service import get_user_timezone
from services.file_service import read_json, write_json, events_path


def list_events(user_name: str, workspace: str = "personal") -> list[dict]:
    return read_json(events_path(user_name, workspace), default={"events": []}).get("events", [])


def get_event(user_name: str, event_id: str, workspace: str = "personal") -> dict | None:
    return next((e for e in list_events(user_name, workspace) if e["id"] == event_id), None)


def add_event(user_name: str, event_data: dict, workspace: str = "personal") -> dict:
    data = read_json(events_path(user_name, workspace), default={"events": []})
    tz = ZoneInfo(get_user_timezone(user_name))
    event: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "title": event_data["title"],
        "start_date": event_data["start_date"],
        "end_date": event_data.get("end_date"),
        "start_time": event_data.get("start_time"),
        "end_time": event_data.get("end_time"),
        "all_day": event_data.get("all_day", True),
        "color": event_data.get("color", "blue"),
        "notes": event_data.get("notes"),
        "created_at": datetime.now(tz).isoformat(),
    }
    for extra in ("created_by",):
        if extra in event_data:
            event[extra] = event_data[extra]
    data["events"].append(event)
    write_json(events_path(user_name, workspace), data)
    return event


def update_event(user_name: str, event_id: str, updates: dict, workspace: str = "personal") -> dict | None:
    data = read_json(events_path(user_name, workspace), default={"events": []})
    for i, event in enumerate(data["events"]):
        if event["id"] == event_id:
            data["events"][i] = {**event, **updates}
            write_json(events_path(user_name, workspace), data)
            return data["events"][i]
    return None


def delete_event(user_name: str, event_id: str, workspace: str = "personal") -> bool:
    data = read_json(events_path(user_name, workspace), default={"events": []})
    original_len = len(data["events"])
    data["events"] = [e for e in data["events"] if e["id"] != event_id]
    if len(data["events"]) == original_len:
        return False
    write_json(events_path(user_name, workspace), data)
    return True
