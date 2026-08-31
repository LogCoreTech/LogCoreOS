"""Tests for tasks:m032_migrate_recurrence_to_structured_rule — converts every
recurring task's legacy daily/weekly/monthly string into the structured
RecurrenceRule shape, across every real user, both workspaces, and both pool
pseudo-users. Mirrors goals/tests' own coverage shape for m031."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from module_packages.tasks.manifest import m032_migrate_recurrence_to_structured_rule
from services import auth_service
from services.file_service import read_json, tasks_path, write_json

USER = "MigrationUser"


def _seed_features_json(brain):
    write_json(brain / "_system" / "features.json", {"profile": "personal", "roles": {}})


def _seed_task(brain, store_user, workspace, task_id, recurrence, due_date):
    path = tasks_path(store_user, workspace)
    data = read_json(path, default={"tasks": []})
    data["tasks"].append(
        {
            "id": task_id,
            "title": task_id,
            "type": "recurring",
            "recurrence": recurrence,
            "status": "pending",
            "due_date": due_date,
        }
    )
    write_json(path, data)


def test_converts_daily_weekly_monthly_across_real_user(brain):
    auth_service.create_user("mig@example.com", "pw", USER)
    _seed_features_json(brain)
    _seed_task(brain, USER, "personal", "d1", "daily", "2024-06-01")
    # 2024-06-05 is a Wednesday
    _seed_task(brain, USER, "personal", "w1", "weekly", "2024-06-05")
    _seed_task(brain, USER, "personal", "m1", "monthly", "2024-06-15")

    m032_migrate_recurrence_to_structured_rule(brain)

    tasks = {t["id"]: t for t in read_json(tasks_path(USER))["tasks"]}
    assert tasks["d1"]["recurrence"] == {"freq": "daily", "interval": 1}
    assert tasks["w1"]["recurrence"] == {"freq": "weekly", "interval": 1, "weekdays": ["WE"]}
    assert tasks["m1"]["recurrence"] == {"freq": "monthly", "interval": 1, "month_day": 15}


def test_converts_household_and_team_pool_stores(brain):
    _seed_features_json(brain)
    _seed_task(brain, "_household", "personal", "hh1", "daily", "2024-06-01")
    _seed_task(brain, "_team", "personal", "tm1", "daily", "2024-06-01")

    m032_migrate_recurrence_to_structured_rule(brain)

    hh_tasks = {t["id"]: t for t in read_json(tasks_path("_household", "personal"))["tasks"]}
    tm_tasks = {t["id"]: t for t in read_json(tasks_path("_team", "personal"))["tasks"]}
    assert hh_tasks["hh1"]["recurrence"] == {"freq": "daily", "interval": 1}
    assert tm_tasks["tm1"]["recurrence"] == {"freq": "daily", "interval": 1}


def test_already_structured_recurrence_is_left_untouched(brain):
    auth_service.create_user("mig2@example.com", "pw", USER)
    _seed_features_json(brain)
    rule = {"freq": "weekly", "interval": 2, "weekdays": ["MO", "FR"]}
    _seed_task(brain, USER, "personal", "already", rule, "2024-06-03")

    m032_migrate_recurrence_to_structured_rule(brain)

    tasks = {t["id"]: t for t in read_json(tasks_path(USER))["tasks"]}
    assert tasks["already"]["recurrence"] == rule


def test_idempotent_on_second_run(brain):
    auth_service.create_user("mig3@example.com", "pw", USER)
    _seed_features_json(brain)
    _seed_task(brain, USER, "personal", "d1", "daily", "2024-06-01")

    m032_migrate_recurrence_to_structured_rule(brain)
    first = read_json(tasks_path(USER))["tasks"][0]["recurrence"]
    m032_migrate_recurrence_to_structured_rule(brain)
    second = read_json(tasks_path(USER))["tasks"][0]["recurrence"]

    assert first == second == {"freq": "daily", "interval": 1}


def test_noop_on_a_store_with_no_recurring_tasks(brain):
    auth_service.create_user("mig4@example.com", "pw", USER)
    _seed_features_json(brain)
    # No tasks.json exists yet for this user at all.
    m032_migrate_recurrence_to_structured_rule(brain)  # must not raise
    assert read_json(tasks_path(USER), default={"tasks": []})["tasks"] == []
