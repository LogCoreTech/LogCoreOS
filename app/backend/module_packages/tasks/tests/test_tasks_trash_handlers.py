"""Tests for tasks/backend/trash_handlers.py — the per-module side of the
trash registry contract (see services/trash_service.py's module docstring
and module_registry.py's trash_dispatch()/owned_trash_types)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.tasks.backend import trash_handlers
from module_packages.tasks.manifest import MODULE
from services import auth_service, task_service

USER = "TestUser"


@pytest.fixture()
def user_brain(brain):
    user_dir = brain / "USERS" / USER / "Tasks"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def test_record_types_match_manifest():
    assert trash_handlers.RECORD_TYPES == MODULE.owned_trash_types


def test_describe_uses_title_and_category():
    title, subtitle = trash_handlers.describe(
        "task", {"title": "Water the plants", "category": "Home"}
    )
    assert title == "Water the plants"
    assert subtitle == "Tasks · Home"


def test_describe_handles_missing_category():
    title, subtitle = trash_handlers.describe("task", {"title": "Untagged"})
    assert title == "Untagged"
    assert subtitle == "Tasks"


def test_restore_reinserts_task(user_brain):
    task = task_service.add_task(USER, {"title": "Buy milk", "category": "Errands"})
    entry = {"payload": task}

    task_service.delete_task(USER, task["id"], deleted_by=USER)
    assert task_service.get_task(USER, task["id"]) is None

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["id"] == task["id"]
    assert task_service.get_task(USER, task["id"]) is not None


def test_restore_conflict_raises_when_id_already_present(user_brain):
    task = task_service.add_task(USER, {"title": "Duplicate", "category": "Work"})
    entry = {"payload": task}

    with pytest.raises(ValueError):
        trash_handlers.restore(USER, "personal", entry)


def test_access_check_always_true():
    assert trash_handlers.access_check({"name": USER}, "personal", {}) is True
