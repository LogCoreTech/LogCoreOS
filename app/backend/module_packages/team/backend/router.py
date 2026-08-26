"""Team module — shared business task and event pool for all users with the 'team' module."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from routers._event_models import EventCreate, EventUpdate
from routers._task_models import TaskCreateBase, TaskUpdateBase
from routers.auth import require_module, require_pool_edit
from services import auth_service, events_service, task_service
from services.file_service import events_path, tasks_path, write_json
from services.rate_limiter import rate_limit

_require_team = require_module("team")
# Write access: admins always; members only if granted team pool management.
_require_team_edit = require_pool_edit("team")
_write_limit = rate_limit(30, 60)

router = APIRouter()

_TEAM = "_team"


def _ensure_team() -> None:
    path = tasks_path(_TEAM)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, {"tasks": []})


def _ensure_team_events() -> None:
    path = events_path(_TEAM)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, {"events": []})


class TeamTaskCreate(TaskCreateBase):
    pass


class TeamTaskUpdate(TaskUpdateBase):
    pass


def _validate_task_id(task_id: str) -> str:
    try:
        UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    return task_id


def _validate_event_id(event_id: str) -> str:
    try:
        UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID format")
    return event_id


@router.get("/tasks")
def list_team_tasks(current_user: dict = Depends(_require_team)):
    _ensure_team()
    return task_service.list_tasks(_TEAM)


@router.post("/tasks")
def add_team_task(
    req: TeamTaskCreate,
    current_user: dict = Depends(_require_team_edit),
    _rl: None = Depends(_write_limit),
):
    _ensure_team()
    payload = req.model_dump()
    payload["created_by"] = current_user["name"]
    return task_service.add_task(_TEAM, payload)


@router.patch("/tasks/{task_id}")
def update_team_task(
    task_id: str,
    req: TeamTaskUpdate,
    current_user: dict = Depends(_require_team_edit),
    _rl: None = Depends(_write_limit),
):
    _validate_task_id(task_id)
    _ensure_team()
    updates = req.model_dump(exclude_unset=True)
    if updates.get("status") in ("done", "skipped"):
        updates["completed_by"] = current_user["name"]
    result = task_service.update_task(_TEAM, task_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/tasks/{task_id}")
def delete_team_task(
    task_id: str,
    current_user: dict = Depends(_require_team_edit),
    _rl: None = Depends(_write_limit),
):
    _validate_task_id(task_id)
    _ensure_team()
    if not task_service.delete_task(_TEAM, task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}


@router.get("/members")
def list_team_members(current_user: dict = Depends(_require_team_edit)):
    """Member names for the assignment dropdown. Visible to admins + granted users."""
    return [{"name": u["name"]} for u in auth_service.list_users()]


# ---------------------------------------------------------------------------
# Team events (admin write, all members read)
# ---------------------------------------------------------------------------


@router.get("/events")
def list_team_events(current_user: dict = Depends(_require_team)):
    _ensure_team_events()
    return events_service.list_events(_TEAM)


@router.post("/events", status_code=201)
def add_team_event(
    req: EventCreate,
    current_user: dict = Depends(_require_team_edit),
    _rl: None = Depends(_write_limit),
):
    _ensure_team_events()
    payload = req.model_dump()
    payload["created_by"] = current_user["name"]
    return events_service.add_event(_TEAM, payload)


@router.patch("/events/{event_id}")
def update_team_event(
    event_id: str,
    req: EventUpdate,
    current_user: dict = Depends(_require_team_edit),
    _rl: None = Depends(_write_limit),
):
    _validate_event_id(event_id)
    result = events_service.update_event(_TEAM, event_id, req.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Event not found")
    return result


@router.delete("/events/{event_id}", status_code=204)
def delete_team_event(
    event_id: str,
    current_user: dict = Depends(_require_team_edit),
    _rl: None = Depends(_write_limit),
):
    _validate_event_id(event_id)
    if not events_service.delete_event(_TEAM, event_id):
        raise HTTPException(status_code=404, detail="Event not found")
