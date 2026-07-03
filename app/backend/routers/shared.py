"""Shared household task and event pool — readable and writable by all authenticated users."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from routers.auth import require_module, require_pool_edit
from routers._task_models import TaskCreateBase, TaskUpdateBase
from routers._event_models import EventCreate, EventUpdate
from services import task_service, events_service, auth_service
from services.file_service import tasks_path, events_path, write_json
from services.rate_limiter import rate_limit

_require_household = require_module("household")
# Write access: admins always; members only if granted household pool management.
_require_household_edit = require_pool_edit("household")
_write_limit = rate_limit(30, 60)

router = APIRouter()

_HOUSEHOLD = "_household"


def _ensure_household_events() -> None:
    path = events_path(_HOUSEHOLD)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, {"events": []})


def _ensure_household() -> None:
    """Create the household Tasks dir if it doesn't exist yet."""
    path = tasks_path(_HOUSEHOLD)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, {"tasks": []})


class SharedTaskCreate(TaskCreateBase):
    pass


class SharedTaskUpdate(TaskUpdateBase):
    pass


def _validate_task_id(task_id: str) -> str:
    try:
        UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    return task_id


@router.get("/tasks")
def list_shared(current_user: dict = Depends(_require_household)):
    _ensure_household()
    return task_service.list_tasks(_HOUSEHOLD)


@router.post("/tasks")
def add_shared(
    req: SharedTaskCreate,
    current_user: dict = Depends(_require_household_edit),
    _rl: None = Depends(_write_limit),
):
    _ensure_household()
    payload = req.model_dump()
    payload["created_by"] = current_user["name"]
    return task_service.add_task(_HOUSEHOLD, payload)


@router.patch("/tasks/{task_id}")
def update_shared(
    task_id: str,
    req: SharedTaskUpdate,
    current_user: dict = Depends(_require_household_edit),
    _rl: None = Depends(_write_limit),
):
    _validate_task_id(task_id)
    _ensure_household()
    updates = req.model_dump(exclude_unset=True)
    if updates.get("status") in ("done", "skipped"):
        updates["completed_by"] = current_user["name"]
    result = task_service.update_task(_HOUSEHOLD, task_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/tasks/{task_id}")
def delete_shared(
    task_id: str,
    current_user: dict = Depends(_require_household_edit),
    _rl: None = Depends(_write_limit),
):
    _validate_task_id(task_id)
    _ensure_household()
    if not task_service.delete_task(_HOUSEHOLD, task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}


@router.get("/members")
def list_household_members(current_user: dict = Depends(_require_household_edit)):
    """Member names for the assignment dropdown. Visible to admins + granted users."""
    return [{"name": u["name"]} for u in auth_service.list_users()]


# ---------------------------------------------------------------------------
# Household events (admin write, all members read)
# ---------------------------------------------------------------------------


def _validate_event_id(event_id: str) -> str:
    try:
        UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID format")
    return event_id


@router.get("/events")
def list_household_events(current_user: dict = Depends(_require_household)):
    _ensure_household_events()
    return events_service.list_events(_HOUSEHOLD)


@router.post("/events", status_code=201)
def add_household_event(
    req: EventCreate,
    current_user: dict = Depends(_require_household_edit),
    _rl: None = Depends(_write_limit),
):
    _ensure_household_events()
    payload = req.model_dump()
    payload["created_by"] = current_user["name"]
    return events_service.add_event(_HOUSEHOLD, payload)


@router.patch("/events/{event_id}")
def update_household_event(
    event_id: str,
    req: EventUpdate,
    current_user: dict = Depends(_require_household_edit),
    _rl: None = Depends(_write_limit),
):
    _validate_event_id(event_id)
    result = events_service.update_event(_HOUSEHOLD, event_id, req.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Event not found")
    return result


@router.delete("/events/{event_id}", status_code=204)
def delete_household_event(
    event_id: str,
    current_user: dict = Depends(_require_household_edit),
    _rl: None = Depends(_write_limit),
):
    _validate_event_id(event_id)
    if not events_service.delete_event(_HOUSEHOLD, event_id):
        raise HTTPException(status_code=404, detail="Event not found")
