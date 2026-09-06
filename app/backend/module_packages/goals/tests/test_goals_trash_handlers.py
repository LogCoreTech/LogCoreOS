"""Tests for goals/backend/trash_handlers.py — the per-module side of the
trash registry contract (see services/trash_service.py's module docstring
and module_registry.py's trash_dispatch()/owned_trash_types)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.goals.backend import trash_handlers
from module_packages.goals.backend.service import create_goal, delete_goal, get_goal, list_goals
from module_packages.goals.manifest import MODULE
from services import auth_service

USER = "TestUser"


@pytest.fixture()
def user_brain(brain):
    from services import mod_store_service

    mod_store_service.mark_installed("goals", by="test-fixture")
    user_dir = brain / "USERS" / USER / "Goals"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def _make_goal(**kwargs):
    base = {"title": "Run a marathon", "due_date": "2026-12-31"}
    return {**base, **kwargs}


def test_record_types_match_manifest():
    assert trash_handlers.RECORD_TYPES == MODULE.owned_trash_types


def test_describe_uses_title():
    title, subtitle = trash_handlers.describe("goal", {"title": "Learn Spanish"})
    assert title == "Learn Spanish"
    assert subtitle == "Goals"


def test_restore_reinserts_goal(user_brain):
    goal = create_goal(USER, _make_goal())
    entry = {"payload": goal}

    delete_goal(USER, goal["id"], deleted_by=USER)
    assert get_goal(USER, goal["id"]) is None

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["id"] == goal["id"]
    assert get_goal(USER, goal["id"]) is not None


def test_restore_conflict_raises_when_id_already_present(user_brain):
    goal = create_goal(USER, _make_goal())
    entry = {"payload": goal}

    with pytest.raises(ValueError):
        trash_handlers.restore(USER, "personal", entry)


def test_cascade_delete_writes_one_trash_entry_per_goal(user_brain):
    parent = create_goal(USER, _make_goal(title="Parent"))
    child = create_goal(USER, _make_goal(title="Child", parent_id=parent["id"]))

    delete_goal(USER, parent["id"], cascade=True, deleted_by=USER)

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    ids = {e["original_id"] for e in entries}
    assert parent["id"] in ids
    assert child["id"] in ids
    assert list_goals(USER) == []


def test_access_check_always_true():
    assert trash_handlers.access_check({"name": USER}, "personal", {}) is True
