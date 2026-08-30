"""Router-level tests for module_packages/goals/backend/router.py — personal
+ pool CRUD, the explicit `pool: bool` flag routing (not id-inference), and
pool_edit write gating. Endpoint functions called directly with a
pre-resolved user dict + plain workspace string, matching this suite's
established convention (see test_contacts_router.py/test_assets_router.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.goals.backend.router import (
    GoalCreate,
    GoalUpdate,
    MetricLog,
    create_goal,
    delete_goal,
    get_goal,
    list_goals,
    list_metric_providers,
    log_metric_value,
    update_goal,
)


@pytest.fixture()
def users(brain):
    from services import auth_service, mod_store_service

    mod_store_service.mark_installed("goals", by="test-fixture")
    mod_store_service.mark_installed("household", by="test-fixture")
    admin = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": admin, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_create_and_list_personal_goal(users):
    created = create_goal(GoalCreate(title="Read 20 books"), users["bob"], "personal")
    assert created["title"] == "Read 20 books"

    listed = list_goals(users["bob"], "personal")
    assert any(g["id"] == created["id"] for g in listed)
    # Not visible to Alice, who didn't create it and it isn't pool
    assert not any(g["id"] == created["id"] for g in list_goals(users["alice"], "personal"))


def test_get_goal_returns_detail_with_progress(users):
    created = create_goal(GoalCreate(title="Detail check"), users["bob"], "personal")
    detail = get_goal(created["id"], False, users["bob"], "personal")
    assert detail["goal"]["id"] == created["id"]
    assert detail["progress"]["pct"] == 0
    assert detail["subgoals"] == []
    assert detail["linked_tasks"] == []


def test_get_goal_404_when_missing(users):
    with pytest.raises(HTTPException) as exc:
        get_goal("11111111-1111-1111-1111-111111111111", False, users["bob"], "personal")
    assert exc.value.status_code == 404


def test_update_goal(users):
    created = create_goal(GoalCreate(title="Old"), users["bob"], "personal")
    result = update_goal(created["id"], GoalUpdate(title="New"), users["bob"], "personal")
    assert result["title"] == "New"


def test_delete_goal_default_choice(users):
    created = create_goal(GoalCreate(title="Temp"), users["bob"], "personal")
    result = delete_goal(created["id"], False, False, False, users["bob"], "personal")
    assert result["ok"] is True
    assert not any(g["id"] == created["id"] for g in list_goals(users["bob"], "personal"))


def test_metric_log_on_manual_goal(users):
    created = create_goal(
        GoalCreate(title="Weight", metric={"provider": "manual", "config": {"target_value": 150}}),
        users["bob"],
        "personal",
    )
    result = log_metric_value(
        created["id"], MetricLog(value=160, date="2026-01-01"), users["bob"], "personal"
    )
    assert result["metric"]["history"][-1]["value"] == 160


def test_list_metric_providers_includes_manual(users):
    providers = list_metric_providers(users["bob"])
    keys = [p["key"] for p in providers]
    assert "manual" in keys


# ---------------------------------------------------------------------------
# Pool goals — explicit pool=True routing + pool_edit gating
# ---------------------------------------------------------------------------


def test_create_pool_goal_requires_pool_edit_or_admin(users):
    with pytest.raises(HTTPException) as exc:
        create_goal(GoalCreate(title="Pool goal", pool=True), users["bob"], "personal")
    assert exc.value.status_code == 403


def test_admin_can_always_create_pool_goal(users):
    created = create_goal(GoalCreate(title="Family goal", pool=True), users["alice"], "personal")
    assert created["title"] == "Family goal"

    # Visible to both alice and bob via the merged personal+pool list
    bob_list = list_goals(users["bob"], "personal")
    assert any(g["id"] == created["id"] and g["_owner"] == "_household" for g in bob_list)


def test_member_with_pool_edit_grant_can_create_pool_goal(users):
    from services import auth_service

    auth_service.update_user(users["bob"]["id"], {"pool_edit": ["household"]})
    bob = auth_service.get_user_by_name("Bob")

    created = create_goal(GoalCreate(title="Granted", pool=True), bob, "personal")
    assert created["title"] == "Granted"


def test_pool_goal_hidden_when_household_not_installed(users):
    from services import mod_store_service

    mod_store_service.mark_uninstalled("household", by="test-fixture")
    result = list_goals(users["bob"], "personal")
    assert result == []  # bob's own list is empty, and no pool leakage/crash
