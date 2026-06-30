"""Calendar module — personal tasks and events with calendar module guard."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from routers._event_models import EventCreate, EventUpdate
from routers.auth import get_workspace, require_module
from services import events_service, task_service
from services.rate_limiter import rate_limit

_require_calendar = require_module("calendar")
_write_limit = rate_limit(30, 60)

router = APIRouter()


def _validate_event_id(event_id: str) -> str:
    try:
        UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID format")
    return event_id


# ---------------------------------------------------------------------------
# Tasks (existing)
# ---------------------------------------------------------------------------


@router.get("/tasks")
def calendar_tasks(
    current_user: dict = Depends(_require_calendar),
    workspace: str = Depends(get_workspace),
):
    """Return user tasks for calendar display."""
    return task_service.list_tasks(current_user["name"], workspace)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@router.get("/events")
def list_events(
    current_user: dict = Depends(_require_calendar),
    workspace: str = Depends(get_workspace),
):
    return events_service.list_events(current_user["name"], workspace)


@router.post("/events", status_code=201)
def add_event(
    req: EventCreate,
    current_user: dict = Depends(_require_calendar),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    return events_service.add_event(current_user["name"], req.model_dump(), workspace)


@router.get("/events/{event_id}")
def get_event(
    event_id: str,
    current_user: dict = Depends(_require_calendar),
    workspace: str = Depends(get_workspace),
):
    _validate_event_id(event_id)
    event = events_service.get_event(current_user["name"], event_id, workspace)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/events/{event_id}")
def update_event(
    event_id: str,
    req: EventUpdate,
    current_user: dict = Depends(_require_calendar),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_event_id(event_id)
    result = events_service.update_event(
        current_user["name"], event_id, req.model_dump(exclude_unset=True), workspace
    )
    if not result:
        raise HTTPException(status_code=404, detail="Event not found")
    return result


@router.delete("/events/{event_id}", status_code=204)
def delete_event(
    event_id: str,
    current_user: dict = Depends(_require_calendar),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_event_id(event_id)
    if not events_service.delete_event(current_user["name"], event_id, workspace):
        raise HTTPException(status_code=404, detail="Event not found")
