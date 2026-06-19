"""Calendar module — serves task data with calendar module guard enforcement."""
from fastapi import APIRouter, Depends

from routers.auth import require_module
from services import task_service

_require_calendar = require_module("calendar")

router = APIRouter()


@router.get("/tasks")
def calendar_tasks(current_user: dict = Depends(_require_calendar)):
    """Return user tasks for calendar display."""
    return task_service.list_tasks(current_user["name"])
