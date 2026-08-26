"""Router-level tests for module_packages/household/backend/router.py — the
first-ever coverage of this endpoint's own CRUD logic (task_service/
events_service themselves are already covered by test_task_service.py/
test_events_service.py; this file is about the router's own behavior:
created_by/completed_by attribution, 404/400 handling, and that the
household pool is genuinely isolated from the team pool).

Endpoint functions are called directly with a pre-resolved user dict,
matching this test suite's established convention (see
test_mod_store_router.py) — Depends(_require_household)/
Depends(_require_household_edit) are bypassed the same way
Depends(require_admin) already is elsewhere; this file tests the
endpoints' own body logic, not the require_module/require_pool_edit
dependency chain itself (untested anywhere in this suite today, a
pre-existing, systemic gap this conversion isn't scoped to close)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.household.backend.router import (
    SharedTaskCreate,
    SharedTaskUpdate,
    add_household_event,
    add_shared,
    delete_household_event,
    delete_shared,
    list_household_events,
    list_shared,
    update_household_event,
    update_shared,
)
from routers._event_models import EventCreate, EventUpdate


@pytest.fixture()
def member(brain):
    from services import auth_service

    return auth_service.create_user("alice@example.com", "password123", "Alice")


def test_add_and_list_task_sets_created_by(member):
    add_shared(SharedTaskCreate(title="Groceries", category="Home"), member)

    tasks = list_shared(member)

    assert len(tasks) == 1
    assert tasks[0]["title"] == "Groceries"
    assert tasks[0]["created_by"] == "Alice"


def test_update_task_marks_completed_by(member):
    task = add_shared(SharedTaskCreate(title="Dishes", category="Home"), member)

    result = update_shared(task["id"], SharedTaskUpdate(status="done"), member)

    assert result["status"] == "done"
    assert result["completed_by"] == "Alice"


def test_update_task_not_found_404(member):
    with pytest.raises(HTTPException) as exc:
        update_shared("11111111-1111-1111-1111-111111111111", SharedTaskUpdate(title="x"), member)
    assert exc.value.status_code == 404


def test_update_task_invalid_id_400(member):
    with pytest.raises(HTTPException) as exc:
        update_shared("not-a-uuid", SharedTaskUpdate(title="x"), member)
    assert exc.value.status_code == 400


def test_delete_task(member):
    task = add_shared(SharedTaskCreate(title="Sweep", category="Home"), member)

    result = delete_shared(task["id"], member)

    assert result == {"ok": True}
    assert list_shared(member) == []


def test_delete_task_not_found_404(member):
    with pytest.raises(HTTPException) as exc:
        delete_shared("11111111-1111-1111-1111-111111111111", member)
    assert exc.value.status_code == 404


def test_add_and_list_event_sets_created_by(member):
    add_household_event(EventCreate(title="Family dinner", start_date="2026-09-01"), member)

    events = list_household_events(member)

    assert len(events) == 1
    assert events[0]["title"] == "Family dinner"
    assert events[0]["created_by"] == "Alice"


def test_update_event(member):
    event = add_household_event(EventCreate(title="Dentist", start_date="2026-09-01"), member)

    result = update_household_event(event["id"], EventUpdate(title="Dentist (Bob)"), member)

    assert result["title"] == "Dentist (Bob)"


def test_update_event_not_found_404(member):
    with pytest.raises(HTTPException) as exc:
        update_household_event(
            "11111111-1111-1111-1111-111111111111", EventUpdate(title="x"), member
        )
    assert exc.value.status_code == 404


def test_delete_event(member):
    event = add_household_event(EventCreate(title="Cleanup", start_date="2026-09-01"), member)

    delete_household_event(event["id"], member)

    assert list_household_events(member) == []


def test_household_pool_isolated_from_team_pool(member):
    """The real guarantee AGENTS.md documents: 'no data can cross between
    the two.' Household writes must never appear in a Team query, using
    the real task_service store both pools actually read from."""
    from services import task_service

    add_shared(SharedTaskCreate(title="Household only", category="Home"), member)

    assert task_service.list_tasks("_household")[0]["title"] == "Household only"
    assert task_service.list_tasks("_team") == []
