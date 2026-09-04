"""Tests for suggestions_service.py's this_week_digest (item #6, 2026-09-04
UX Polish Batch) — config defaults, the runner's own computation, and the
scheduler job's per-user cadence gating."""

import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

# Same stub shape test_suggestions_service.py already uses (avoids a broken
# jose/cryptography import in CI) — setdefault means whichever test file
# imports first wins, so this must match that file's stub exactly.
_mock_auth = MagicMock()
_mock_auth.get_user_by_name.return_value = None
_mock_auth.today_for_user.return_value = date.today()
_mock_auth.get_user_timezone.return_value = "UTC"
sys.modules.setdefault("services.auth_service", _mock_auth)
# setdefault is a no-op if another test file's stub already claimed this slot
# first (collection order dependent) — configure whichever instance actually
# won, not necessarily the local _mock_auth above, or events_service's own
# get_user_timezone() call returns an unconfigured MagicMock and ZoneInfo()
# blows up.
sys.modules["services.auth_service"].get_user_timezone.return_value = "UTC"

import services.suggestions_service as svc
from services.events_service import add_event
from services.file_service import history_path, write_json

USER = "TestUser"


@pytest.fixture()
def user_dir(brain):
    d = brain / "USERS" / USER
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_config_default_is_off_and_weekly(user_dir):
    cfg = svc.get_config(USER)
    assert "this_week_digest" in cfg
    assert cfg["this_week_digest"]["enabled"] is False  # opt-in, unlike the other builtins
    assert cfg["this_week_digest"]["cadence"] == "weekly"


def test_cadence_is_independently_configurable(user_dir):
    svc.update_config(USER, "this_week_digest", {"enabled": True, "cadence": "daily"})
    cfg = svc.get_config(USER)
    assert cfg["this_week_digest"]["enabled"] is True
    assert cfg["this_week_digest"]["cadence"] == "daily"


def test_run_reports_nothing_when_no_activity(user_dir):
    result = svc._run_this_week_digest(USER, svc.get_config(USER)["this_week_digest"])
    assert result == {"ok": False, "reason": "nothing to report"}


def test_run_counts_completed_tasks_this_week(user_dir):
    today = date.today()
    write_json(
        history_path(USER, "personal"),
        {
            "tasks": [
                {"id": "1", "title": "Water plants", "completed_at": today.isoformat()},
                {
                    "id": "2",
                    "title": "Old task",
                    "completed_at": (today - timedelta(days=30)).isoformat(),
                },
            ]
        },
    )

    result = svc._run_this_week_digest(USER, svc.get_config(USER)["this_week_digest"])

    assert result["ok"] is True
    assert result["completed"] == 1  # only the recent one, the 30-day-old one is out of window
    assert result["upcoming"] == 0


def test_run_counts_upcoming_events_next_7_days(user_dir):
    today = date.today()
    add_event(
        USER,
        {"title": "Dentist", "start_date": (today + timedelta(days=2)).isoformat()},
    )
    add_event(
        USER,
        {"title": "Next month", "start_date": (today + timedelta(days=40)).isoformat()},
    )

    result = svc._run_this_week_digest(USER, svc.get_config(USER)["this_week_digest"])

    assert result["ok"] is True
    assert result["completed"] == 0
    assert result["upcoming"] == 1  # only the one inside the 7-day window


def test_run_is_a_noop_when_disabled_via_dispatch(user_dir):
    result = svc.run_suggestion_sync(USER, "this_week_digest")
    assert result == {"ok": False, "reason": "disabled"}  # default is off


def test_run_fires_via_dispatch_once_enabled(user_dir):
    svc.update_config(USER, "this_week_digest", {"enabled": True})
    today = date.today()
    add_event(USER, {"title": "Dentist", "start_date": (today + timedelta(days=1)).isoformat()})

    result = svc.run_suggestion_sync(USER, "this_week_digest")

    assert result["ok"] is True
    assert result["fired"] == "this_week_digest"
