"""Tests for the nightly recurring-task processor (services/recurring_service.py).
Date-math itself lives in services/recurrence_engine.py and is tested there —
this file covers process_user()'s own orchestration: advancing, streak-breaking,
and the missed-occurrence log entry."""

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import auth_service
from services.file_service import read_json, tasks_path, write_json
from services.recurring_service import process_user

REC_USER = "RecurringUser"
DAILY_RULE = {"freq": "daily", "interval": 1}


def _seed_recurring(brain, tasks: list[dict]) -> None:
    user_dir = brain / "USERS" / REC_USER / "Tasks"
    user_dir.mkdir(parents=True, exist_ok=True)
    write_json(tasks_path(REC_USER), {"tasks": tasks})


def _task_row(
    title: str,
    status: str,
    due: str,
    last_completed: str | None = None,
    streak: int = 0,
    recurrence: dict | None = None,
    completion_log: list[dict] | None = None,
) -> dict:
    return {
        "id": title,
        "title": title,
        "type": "recurring",
        "recurrence": recurrence or DAILY_RULE,
        "status": status,
        "due_date": due,
        "last_completed_date": last_completed,
        "streak_count": streak,
        "completion_log": completion_log or [],
    }


@pytest.fixture()
def rec_brain(brain):
    auth_service.create_user("rec@example.com", "pw", REC_USER)
    return brain


def test_process_user_advances_task_completed_yesterday(rec_brain):
    # The nightly 00:01 run advances recurring tasks completed on a *previous* day
    today = auth_service.today_for_user(REC_USER)
    yesterday = (today - timedelta(days=1)).isoformat()
    _seed_recurring(
        rec_brain,
        [
            _task_row("Daily", "done", yesterday, last_completed=yesterday),
        ],
    )
    result = process_user(REC_USER)
    assert result["advanced"] == 1
    tasks = read_json(tasks_path(REC_USER))["tasks"]
    assert tasks[0]["status"] == "pending"
    assert tasks[0]["due_date"] > yesterday


def test_process_user_leaves_task_completed_today(rec_brain):
    # A task completed today stays done until tomorrow's nightly run
    today = auth_service.today_for_user(REC_USER).isoformat()
    _seed_recurring(
        rec_brain,
        [
            _task_row("Daily", "done", today, last_completed=today),
        ],
    )
    result = process_user(REC_USER)
    assert result["advanced"] == 0
    tasks = read_json(tasks_path(REC_USER))["tasks"]
    assert tasks[0]["status"] == "done"


def test_process_user_breaks_streak_on_missed_task(rec_brain):
    past_due = "2020-01-01"
    _seed_recurring(
        rec_brain,
        [
            _task_row("Missed", "pending", past_due, streak=5),
        ],
    )
    result = process_user(REC_USER)
    assert result["broken_streaks"] == 1
    tasks = read_json(tasks_path(REC_USER))["tasks"]
    assert tasks[0]["streak_count"] == 0


def test_process_user_logs_missed_occurrence(rec_brain):
    past_due = "2020-01-01"
    _seed_recurring(
        rec_brain,
        [
            _task_row("Missed", "pending", past_due, streak=5),
        ],
    )
    process_user(REC_USER)
    tasks = read_json(tasks_path(REC_USER))["tasks"]
    log = tasks[0]["completion_log"]
    assert {"date": past_due, "status": "missed"} in log


def test_process_user_missed_log_entry_deduped_on_repeat_run(rec_brain):
    # Simulates the same stale due_date being detected twice (e.g. a scheduler
    # hiccup re-running the same night) — the log should never carry two
    # entries for the same date.
    past_due = "2020-01-01"
    _seed_recurring(
        rec_brain,
        [
            _task_row(
                "Missed",
                "pending",
                past_due,
                streak=5,
                completion_log=[{"date": past_due, "status": "missed"}],
            ),
        ],
    )
    process_user(REC_USER)
    tasks = read_json(tasks_path(REC_USER))["tasks"]
    matches = [e for e in tasks[0]["completion_log"] if e["date"] == past_due]
    assert len(matches) == 1


def test_process_user_backfills_missing_due_date(rec_brain):
    # Self-heal: a recurring task somehow missing due_date entirely (pre-fix data, or
    # a bypassed-validation write) gets a real one computed from its rule, not left
    # stuck forever.
    _seed_recurring(
        rec_brain,
        [
            {
                "id": "NoDueDate",
                "title": "NoDueDate",
                "type": "recurring",
                "recurrence": {"freq": "daily", "interval": 1},
                "status": "pending",
                "due_date": None,
                "last_completed_date": None,
                "streak_count": 0,
                "completion_log": [],
            }
        ],
    )
    process_user(REC_USER)
    tasks = read_json(tasks_path(REC_USER))["tasks"]
    today = auth_service.today_for_user(REC_USER).isoformat()
    assert tasks[0]["due_date"] == today


def test_process_user_ignores_non_recurring_tasks(rec_brain):
    user_dir = rec_brain / "USERS" / REC_USER / "Tasks"
    user_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        tasks_path(REC_USER),
        {
            "tasks": [
                {
                    "id": "todo-1",
                    "title": "Regular todo",
                    "type": "todo",
                    "status": "pending",
                    "due_date": "2020-01-01",
                    "recurrence": None,
                    "streak_count": 0,
                    "last_completed_date": None,
                }
            ]
        },
    )
    result = process_user(REC_USER)
    assert result["advanced"] == 0
    assert result["broken_streaks"] == 0


def test_process_user_returns_username(rec_brain):
    _seed_recurring(rec_brain, [])
    result = process_user(REC_USER)
    assert result["user"] == REC_USER


def test_process_user_skips_malformed_task_without_aborting_others(rec_brain):
    # A recurring task with a structurally invalid rule (e.g. a still-broken AI
    # tool call, which bypasses Pydantic validation entirely) must not abort
    # processing of the user's other, valid recurring tasks.
    today = auth_service.today_for_user(REC_USER)
    yesterday = (today - timedelta(days=1)).isoformat()
    _seed_recurring(
        rec_brain,
        [
            _task_row(
                "Broken",
                "pending",
                "2020-01-01",
                recurrence={"freq": "weekly", "interval": 1, "weekdays": []},
            ),
            _task_row("Valid", "done", yesterday, last_completed=yesterday),
        ],
    )
    result = process_user(REC_USER)
    assert result["advanced"] == 1  # the valid task still processed
    tasks = {t["id"]: t for t in read_json(tasks_path(REC_USER))["tasks"]}
    assert tasks["Valid"]["status"] == "pending"
    # The broken task is left untouched, not crashed on.
    assert tasks["Broken"]["due_date"] == "2020-01-01"
