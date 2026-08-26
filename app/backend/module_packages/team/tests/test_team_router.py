"""Router-level tests for module_packages/team/backend/router.py — mirrors
household/tests/test_router.py's own shape exactly, same reasoning
(first-ever coverage of this endpoint's own CRUD logic; permission
dependency chain itself untested here for the same pre-existing,
systemic reason)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.team.backend.router import (
    TeamTaskCreate,
    TeamTaskUpdate,
    add_team_event,
    add_team_task,
    delete_team_event,
    delete_team_task,
    list_team_events,
    list_team_tasks,
    update_team_event,
    update_team_task,
)
from routers._event_models import EventCreate, EventUpdate


@pytest.fixture()
def member(brain):
    from services import auth_service

    return auth_service.create_user("bob@example.com", "password123", "Bob")


def test_add_and_list_task_sets_created_by(member):
    add_team_task(TeamTaskCreate(title="Ship the release", category="Work"), member)

    tasks = list_team_tasks(member)

    assert len(tasks) == 1
    assert tasks[0]["title"] == "Ship the release"
    assert tasks[0]["created_by"] == "Bob"


def test_update_task_marks_completed_by(member):
    task = add_team_task(TeamTaskCreate(title="Review PR", category="Work"), member)

    result = update_team_task(task["id"], TeamTaskUpdate(status="done"), member)

    assert result["status"] == "done"
    assert result["completed_by"] == "Bob"


def test_update_task_not_found_404(member):
    with pytest.raises(HTTPException) as exc:
        update_team_task("11111111-1111-1111-1111-111111111111", TeamTaskUpdate(title="x"), member)
    assert exc.value.status_code == 404


def test_update_task_invalid_id_400(member):
    with pytest.raises(HTTPException) as exc:
        update_team_task("not-a-uuid", TeamTaskUpdate(title="x"), member)
    assert exc.value.status_code == 400


def test_delete_task(member):
    task = add_team_task(TeamTaskCreate(title="Deploy", category="Work"), member)

    result = delete_team_task(task["id"], member)

    assert result == {"ok": True}
    assert list_team_tasks(member) == []


def test_delete_task_not_found_404(member):
    with pytest.raises(HTTPException) as exc:
        delete_team_task("11111111-1111-1111-1111-111111111111", member)
    assert exc.value.status_code == 404


def test_add_and_list_event_sets_created_by(member):
    add_team_event(EventCreate(title="Sprint planning", start_date="2026-09-01"), member)

    events = list_team_events(member)

    assert len(events) == 1
    assert events[0]["title"] == "Sprint planning"
    assert events[0]["created_by"] == "Bob"


def test_update_event(member):
    event = add_team_event(EventCreate(title="Standup", start_date="2026-09-01"), member)

    result = update_team_event(event["id"], EventUpdate(title="Standup (moved)"), member)

    assert result["title"] == "Standup (moved)"


def test_update_event_not_found_404(member):
    with pytest.raises(HTTPException) as exc:
        update_team_event("11111111-1111-1111-1111-111111111111", EventUpdate(title="x"), member)
    assert exc.value.status_code == 404


def test_delete_event(member):
    event = add_team_event(EventCreate(title="Retro", start_date="2026-09-01"), member)

    delete_team_event(event["id"], member)

    assert list_team_events(member) == []


def test_team_pool_isolated_from_household_pool(member):
    from services import task_service

    add_team_task(TeamTaskCreate(title="Team only", category="Work"), member)

    assert task_service.list_tasks("_team")[0]["title"] == "Team only"
    assert task_service.list_tasks("_household") == []
