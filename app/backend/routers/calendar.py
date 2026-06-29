"""Calendar module — personal tasks and events with calendar module guard."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from routers._event_models import EventCreate, EventUpdate
from routers.auth import require_module
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
def calendar_tasks(current_user: dict = Depends(_require_calendar)):
    """Return user tasks for calendar display."""
    return task_service.list_tasks(current_user["name"])


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@router.get("/events")
def list_events(current_user: dict = Depends(_require_calendar)):
    return events_service.list_events(current_user["name"])


@router.post("/events", status_code=201)
def add_event(
    req: EventCreate,
    current_user: dict = Depends(_require_calendar),
    _rl: None = Depends(_write_limit),
):
    return events_service.add_event(current_user["name"], req.model_dump())


@router.get("/events/{event_id}")
def get_event(event_id: str, current_user: dict = Depends(_require_calendar)):
    _validate_event_id(event_id)
    event = events_service.get_event(current_user["name"], event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/events/{event_id}")
def update_event(
    event_id: str,
    req: EventUpdate,
    current_user: dict = Depends(_require_calendar),
    _rl: None = Depends(_write_limit),
):
    _validate_event_id(event_id)
    result = events_service.update_event(
        current_user["name"], event_id, req.model_dump(exclude_unset=True)
    )
    if not result:
        raise HTTPException(status_code=404, detail="Event not found")
    return result


@router.delete("/events/{event_id}", status_code=204)
def delete_event(
    event_id: str,
    current_user: dict = Depends(_require_calendar),
    _rl: None = Depends(_write_limit),
):
    _validate_event_id(event_id)
    if not events_service.delete_event(current_user["name"], event_id):
        raise HTTPException(status_code=404, detail="Event not found")
