"""Tests for dashboard/backend/trash_handlers.py — the per-module side of
the trash registry contract (see services/trash_service.py's module
docstring and module_registry.py's trash_dispatch()/owned_trash_types).
Only whole-dashboard delete is trashable — block removal stays out of scope
(2026-09-05 owner decision)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.dashboard.backend import trash_handlers
from module_packages.dashboard.manifest import MODULE
from services import auth_service
from services.dashboards_service import create_dashboard, delete_dashboard, get_dashboard

USER = "TestUser"


@pytest.fixture()
def user_brain(brain):
    user_dir = brain / "USERS" / USER / "Dashboards"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def test_record_types_match_manifest():
    assert trash_handlers.RECORD_TYPES == MODULE.owned_trash_types


def test_describe_uses_name():
    title, subtitle = trash_handlers.describe("dashboard", {"name": "My Dashboard"})
    assert title == "My Dashboard"
    assert subtitle == "Dashboards"


def test_restore_reinserts_dashboard(user_brain):
    create_dashboard(USER, "personal", USER, "First")
    second = create_dashboard(USER, "personal", USER, "Second")

    delete_dashboard(USER, "personal", second["id"], deleted_by=USER)
    assert get_dashboard(USER, second["id"], "personal") is None

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    entry = next(e for e in entries if e["original_id"] == second["id"])

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["id"] == second["id"]
    assert get_dashboard(USER, second["id"], "personal") is not None


def test_restore_conflict_raises_when_id_already_present(user_brain):
    dashboard = create_dashboard(USER, "personal", USER, "First")
    create_dashboard(USER, "personal", USER, "Second")
    entry = {"payload": dict(dashboard)}

    with pytest.raises(ValueError):
        trash_handlers.restore(USER, "personal", entry)


def test_delete_raises_floor_of_one(user_brain):
    only = create_dashboard(USER, "personal", USER, "Only")
    with pytest.raises(ValueError, match="floor_of_one"):
        delete_dashboard(USER, "personal", only["id"], deleted_by=USER)


def test_access_check_always_true():
    assert trash_handlers.access_check({"name": USER}, "personal", {}) is True
