"""Tests for task CRUD operations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta

import pytest

from services import auth_service, task_service
from services.file_service import read_json, tasks_path, write_json
from services.recurring_service import process_user

USER = "TestUser"


@pytest.fixture()
def user_brain(brain):
    """Create a minimal user brain folder."""
    user_dir = brain / "USERS" / USER / "Tasks"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def _make_task(title="Test Task", category="Work", priority="High"):
    return {
        "title": title,
        "category": category,
        "priority": priority,
        "type": "todo",
        "recurrence": None,
        "due_date": None,
        "due_time": None,
        "notes": None,
    }


def test_add_task(user_brain):
    task = task_service.add_task(USER, _make_task())
    assert task["title"] == "Test Task"
    assert task["status"] == "pending"
    assert "id" in task


def test_list_tasks_returns_added(user_brain):
    task_service.add_task(USER, _make_task("Task A"))
    task_service.add_task(USER, _make_task("Task B"))
    tasks = task_service.list_tasks(USER)
    titles = [t["title"] for t in tasks]
    assert "Task A" in titles
    assert "Task B" in titles


def _backdate_completed(task_id: str, days: int = 1) -> None:
    """Rewind a done task's completed_at so the nightly archiver treats it as yesterday's."""
    data = read_json(tasks_path(USER))
    for t in data["tasks"]:
        if t["id"] == task_id:
            done_at = datetime.fromisoformat(t["completed_at"]) - timedelta(days=days)
            t["completed_at"] = done_at.isoformat()
    write_json(tasks_path(USER), data)


def test_mark_task_done_stays_active_until_nightly_archive(user_brain):
    task = task_service.add_task(USER, _make_task())
    task_service.update_task(USER, task["id"], {"status": "done"})

    # Done non-recurring tasks stay in tasks.json until the 00:01 nightly job
    active = task_service.list_tasks(USER)
    assert any(t["id"] == task["id"] and t["status"] == "done" for t in active)
    assert task_service.list_history(USER) == []

    # Next night: completed_at is now yesterday, so the processor archives it
    _backdate_completed(task["id"])
    process_user(USER)
    active = task_service.list_tasks(USER)
    assert all(t["id"] != task["id"] for t in active)
    history = task_service.list_history(USER)
    assert any(t["id"] == task["id"] for t in history)


def test_update_task_fields(user_brain):
    task = task_service.add_task(USER, _make_task())
    updated = task_service.update_task(USER, task["id"], {"notes": "Some note"})
    assert updated["notes"] == "Some note"


def test_delete_task(user_brain):
    task = task_service.add_task(USER, _make_task())
    result = task_service.delete_task(USER, task["id"])
    assert result is True
    assert task_service.get_task(USER, task["id"]) is None


def test_delete_nonexistent_task(user_brain):
    assert task_service.delete_task(USER, "nonexistent-id") is False


def test_history_pagination(user_brain):
    tasks = [task_service.add_task(USER, _make_task(f"Task {i}")) for i in range(5)]
    for t in tasks:
        task_service.update_task(USER, t["id"], {"status": "done"})
        _backdate_completed(t["id"])
    process_user(USER)  # nightly archive moves them to history

    page1 = task_service.list_history(USER, limit=3, offset=0)
    page2 = task_service.list_history(USER, limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 2
    ids_p1 = {t["id"] for t in page1}
    ids_p2 = {t["id"] for t in page2}
    assert ids_p1.isdisjoint(ids_p2)


def test_history_most_recent_first(user_brain):
    t1 = task_service.add_task(USER, _make_task("First"))
    t2 = task_service.add_task(USER, _make_task("Second"))
    task_service.update_task(USER, t1["id"], {"status": "done"})
    task_service.update_task(USER, t2["id"], {"status": "done"})
    _backdate_completed(t1["id"])
    _backdate_completed(t2["id"])
    process_user(USER)  # nightly archive moves them to history
    history = task_service.list_history(USER)
    # Most recent (t2) should appear before t1
    ids = [t["id"] for t in history]
    assert ids.index(t2["id"]) < ids.index(t1["id"])


def test_update_nonexistent_task_returns_none(user_brain):
    assert task_service.update_task(USER, "no-such-id", {"notes": "hi"}) is None


def test_add_task_with_due_date(user_brain):
    task = task_service.add_task(USER, {**_make_task(), "due_date": "2025-12-31"})
    assert task["due_date"] == "2025-12-31"


def test_add_task_with_notes(user_brain):
    task = task_service.add_task(USER, {**_make_task(), "notes": "important context"})
    assert task["notes"] == "important context"


def test_recurring_task_done_stays_in_active_list(user_brain):
    task = task_service.add_task(
        USER, {**_make_task("Daily"), "type": "recurring", "recurrence": "daily"}
    )
    task_service.update_task(USER, task["id"], {"status": "done"})
    active_ids = [t["id"] for t in task_service.list_tasks(USER)]
    assert task["id"] in active_ids


def test_recurring_task_done_not_moved_to_history(user_brain):
    task = task_service.add_task(
        USER, {**_make_task("Daily"), "type": "recurring", "recurrence": "daily"}
    )
    task_service.update_task(USER, task["id"], {"status": "done"})
    history_ids = [t["id"] for t in task_service.list_history(USER)]
    assert task["id"] not in history_ids


def test_recurring_task_increments_streak(user_brain):
    task = task_service.add_task(
        USER, {**_make_task("Streak"), "type": "recurring", "recurrence": "daily"}
    )
    updated = task_service.update_task(USER, task["id"], {"status": "done"})
    assert updated["streak_count"] == 1


def test_skipped_task_stays_in_active_list(user_brain):
    task = task_service.add_task(USER, _make_task())
    task_service.update_task(USER, task["id"], {"status": "skipped"})
    active_ids = [t["id"] for t in task_service.list_tasks(USER)]
    assert task["id"] in active_ids


def _make_goal(title="Ship v1", category="Work", due_date="2026-12-31"):
    return {
        "title": title,
        "category": category,
        "priority": "High",
        "type": "goal",
        "recurrence": None,
        "due_date": due_date,
        "due_time": None,
        "notes": None,
    }


def test_completed_goals_survive_nightly_sweep(user_brain):
    goal = task_service.add_task(USER, _make_goal())
    task_service.update_task(USER, goal["id"], {"status": "done"})
    _backdate_completed(goal["id"])  # completed "yesterday"
    process_user(USER)  # nightly job runs
    # Goal must still be in tasks.json (Goals "Done" view), NOT swept to history
    active = task_service.list_tasks(USER)
    assert any(t["id"] == goal["id"] for t in active)
    assert task_service.list_history(USER) == []


def test_cleanup_done_goals_archives_only_done_goals(user_brain):
    done_goal = task_service.add_task(USER, _make_goal("Done goal"))
    task_service.update_task(USER, done_goal["id"], {"status": "done"})
    pending_goal = task_service.add_task(USER, _make_goal("Pending goal"))
    done_todo = task_service.add_task(USER, _make_task("Done todo"))
    task_service.update_task(USER, done_todo["id"], {"status": "done"})

    archived = task_service.cleanup_done_goals(USER)
    assert archived == 1
    ids = {t["id"] for t in task_service.list_tasks(USER)}
    assert done_goal["id"] not in ids        # archived
    assert pending_goal["id"] in ids         # untouched
    assert done_todo["id"] in ids            # not a goal — untouched
    assert any(t["id"] == done_goal["id"] for t in task_service.list_history(USER))
