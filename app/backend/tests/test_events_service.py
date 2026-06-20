"""Tests for Calendar events CRUD in services/events_service.py."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

# Stub auth_service before importing events_service to avoid the broken
# jose/cryptography dependency in the local dev environment.
_mock_auth = MagicMock()
_mock_auth.get_user_timezone.return_value = "America/Chicago"
sys.modules.setdefault("services.auth_service", _mock_auth)

from services.file_service import events_path
from services.events_service import (
    list_events,
    get_event,
    add_event,
    update_event,
    delete_event,
)

USER = "EventUser"


def _make_event(**kwargs) -> dict:
    base = {
        "title": "Test Event",
        "start_date": "2026-06-20",
        "end_date": None,
        "start_time": None,
        "end_time": None,
        "all_day": True,
        "color": "blue",
        "notes": None,
    }
    return {**base, **kwargs}


def test_list_events_empty(brain):
    assert list_events(USER) == []


def test_add_event_returns_event(brain):
    ev = add_event(USER, _make_event())
    assert ev["title"] == "Test Event"
    assert ev["color"] == "blue"
    assert "id" in ev
    assert "created_at" in ev


def test_add_event_persists(brain):
    add_event(USER, _make_event(title="Persist"))
    events = list_events(USER)
    assert any(e["title"] == "Persist" for e in events)


def test_add_multiple_events(brain):
    add_event(USER, _make_event(title="A"))
    add_event(USER, _make_event(title="B"))
    assert len(list_events(USER)) == 2


def test_get_event_returns_event(brain):
    ev = add_event(USER, _make_event(title="Get Me"))
    found = get_event(USER, ev["id"])
    assert found is not None
    assert found["title"] == "Get Me"


def test_get_event_missing_returns_none(brain):
    assert get_event(USER, "00000000-0000-0000-0000-000000000000") is None


def test_update_event_changes_field(brain):
    ev = add_event(USER, _make_event(title="Before"))
    updated = update_event(USER, ev["id"], {"title": "After"})
    assert updated["title"] == "After"


def test_update_event_preserves_other_fields(brain):
    ev = add_event(USER, _make_event(color="red", notes="keep me"))
    update_event(USER, ev["id"], {"title": "New Title"})
    found = get_event(USER, ev["id"])
    assert found["color"] == "red"
    assert found["notes"] == "keep me"


def test_update_event_missing_returns_none(brain):
    assert update_event(USER, "00000000-0000-0000-0000-000000000000", {"title": "x"}) is None


def test_delete_event_returns_true(brain):
    ev = add_event(USER, _make_event())
    assert delete_event(USER, ev["id"]) is True


def test_delete_event_removes_from_list(brain):
    ev = add_event(USER, _make_event())
    delete_event(USER, ev["id"])
    assert get_event(USER, ev["id"]) is None


def test_delete_event_missing_returns_false(brain):
    assert delete_event(USER, "00000000-0000-0000-0000-000000000000") is False


def test_events_stored_in_calendar_dir(brain):
    add_event(USER, _make_event())
    assert events_path(USER).exists()
    assert events_path(USER).parent.name == "Calendar"


def test_add_event_with_times(brain):
    ev = add_event(USER, _make_event(all_day=False, start_time="09:00", end_time="10:00"))
    assert ev["all_day"] is False
    assert ev["start_time"] == "09:00"
    assert ev["end_time"] == "10:00"


def test_add_event_with_end_date(brain):
    ev = add_event(USER, _make_event(end_date="2026-06-22"))
    assert ev["end_date"] == "2026-06-22"


def test_household_events_pool(brain):
    """_household pseudo-user works as an events pool."""
    ev = add_event("_household", _make_event(title="Family BBQ"))
    events = list_events("_household")
    assert any(e["title"] == "Family BBQ" for e in events)
    assert get_event("_household", ev["id"]) is not None
