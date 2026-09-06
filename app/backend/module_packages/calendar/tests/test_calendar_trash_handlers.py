"""Tests for calendar/backend/trash_handlers.py — the per-module side of the
trash registry contract (see services/trash_service.py's module docstring
and module_registry.py's trash_dispatch()/owned_trash_types). Covers
Calendar's own events; Household/Team pool events share the same handler
since they call the same core events_service.delete_event()."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.calendar.backend import trash_handlers
from module_packages.calendar.manifest import MODULE
from services import auth_service, events_service

USER = "TestUser"


@pytest.fixture()
def user_brain(brain):
    user_dir = brain / "USERS" / USER / "Calendar"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def _make_event(**kwargs):
    base = {"title": "Test Event", "start_date": "2026-06-20", "all_day": True}
    return {**base, **kwargs}


def test_record_types_match_manifest():
    assert trash_handlers.RECORD_TYPES == MODULE.owned_trash_types


def test_describe_uses_title_and_date():
    title, subtitle = trash_handlers.describe(
        "event", {"title": "Dentist", "start_date": "2026-06-20"}
    )
    assert title == "Dentist"
    assert subtitle == "Calendar · 2026-06-20"


def test_describe_handles_missing_date():
    title, subtitle = trash_handlers.describe("event", {"title": "No date"})
    assert title == "No date"
    assert subtitle == "Calendar"


def test_restore_reinserts_event(user_brain):
    event = events_service.add_event(USER, _make_event())
    entry = {"payload": event}

    events_service.delete_event(USER, event["id"], deleted_by=USER)
    assert events_service.get_event(USER, event["id"]) is None

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["id"] == event["id"]
    assert events_service.get_event(USER, event["id"]) is not None


def test_restore_conflict_raises_when_id_already_present(user_brain):
    event = events_service.add_event(USER, _make_event())
    entry = {"payload": event}

    with pytest.raises(ValueError):
        trash_handlers.restore(USER, "personal", entry)


def test_access_check_always_true():
    assert trash_handlers.access_check({"name": USER}, "personal", {}) is True
