"""Tests for recurring task date arithmetic and the nightly processor."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import auth_service
from services.file_service import write_json, read_json, tasks_path, user_path
from services.recurring_service import _next_due, process_user


def test_daily():
    assert _next_due("2024-01-31", "daily") == "2024-02-01"


def test_weekly():
    assert _next_due("2024-01-01", "weekly") == "2024-01-08"


def test_monthly_normal():
    assert _next_due("2024-01-15", "monthly") == "2024-02-15"


def test_monthly_end_of_month_clamped():
    # Jan 31 → Feb 29 in leap year 2024
    assert _next_due("2024-01-31", "monthly") == "2024-02-29"


def test_monthly_leap_year_feb_to_mar():
    # Feb 29 in leap year → Mar 29
    assert _next_due("2024-02-29", "monthly") == "2024-03-29"


def test_monthly_clamp_non_leap_year():
    # Jan 31, 2025 → Feb 28 (2025 is NOT a leap year)
    assert _next_due("2025-01-31", "monthly") == "2025-02-28"


def test_monthly_century_year_not_leap():
    # 1900 was NOT a leap year (divisible by 100 but not 400)
    assert _next_due("1900-01-31", "monthly") == "1900-02-28"


def test_monthly_400_year_is_leap():
    # 2000 WAS a leap year (divisible by 400)
    assert _next_due("2000-01-31", "monthly") == "2000-02-29"


def test_monthly_year_rollover():
    assert _next_due("2024-12-15", "monthly") == "2025-01-15"


def test_monthly_year_rollover_end_of_month():
    # Dec 31 → Jan 31
    assert _next_due("2024-12-31", "monthly") == "2025-01-31"


def test_unknown_recurrence_falls_back_to_daily():
    assert _next_due("2024-06-01", "unknown") == "2024-06-02"


# ---------------------------------------------------------------------------
# process_user — nightly scheduler integration
# ---------------------------------------------------------------------------

REC_USER = "RecurringUser"


def _seed_recurring(brain, tasks: list[dict]) -> None:
    user_dir = brain / "USERS" / REC_USER / "Tasks"
    user_dir.mkdir(parents=True, exist_ok=True)
    write_json(tasks_path(REC_USER), {"tasks": tasks})


def _task_row(title: str, status: str, due: str, last_completed: str | None = None, streak: int = 0) -> dict:
    return {
        "id": title,
        "title": title,
        "type": "recurring",
        "recurrence": "daily",
        "status": status,
        "due_date": due,
        "last_completed_date": last_completed,
        "streak_count": streak,
    }


@pytest.fixture()
def rec_brain(brain):
    auth_service.create_user("rec@example.com", "pw", REC_USER)
    return brain


def test_process_user_advances_done_task(rec_brain):
    today = auth_service.today_for_user(REC_USER).isoformat()
    _seed_recurring(rec_brain, [
        _task_row("Daily", "done", today, last_completed=today),
    ])
    result = process_user(REC_USER)
    assert result["advanced"] == 1
    tasks = read_json(tasks_path(REC_USER))["tasks"]
    assert tasks[0]["status"] == "pending"
    assert tasks[0]["due_date"] > today


def test_process_user_breaks_streak_on_missed_task(rec_brain):
    today = auth_service.today_for_user(REC_USER).isoformat()
    yesterday = _next_due(today, "daily")  # one day ahead; use a past date instead
    past_due = "2020-01-01"
    _seed_recurring(rec_brain, [
        _task_row("Missed", "pending", past_due, streak=5),
    ])
    result = process_user(REC_USER)
    assert result["broken_streaks"] == 1
    tasks = read_json(tasks_path(REC_USER))["tasks"]
    assert tasks[0]["streak_count"] == 0


def test_process_user_ignores_non_recurring_tasks(rec_brain):
    today = auth_service.today_for_user(REC_USER).isoformat()
    user_dir = rec_brain / "USERS" / REC_USER / "Tasks"
    user_dir.mkdir(parents=True, exist_ok=True)
    write_json(tasks_path(REC_USER), {"tasks": [{
        "id": "todo-1",
        "title": "Regular todo",
        "type": "todo",
        "status": "pending",
        "due_date": "2020-01-01",
        "recurrence": None,
        "streak_count": 0,
        "last_completed_date": None,
    }]})
    result = process_user(REC_USER)
    assert result["advanced"] == 0
    assert result["broken_streaks"] == 0


def test_process_user_returns_username(rec_brain):
    _seed_recurring(rec_brain, [])
    result = process_user(REC_USER)
    assert result["user"] == REC_USER
