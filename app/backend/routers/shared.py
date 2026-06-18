"""Shared household task pool — readable and writable by all authenticated users."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from routers.auth import require_module
from routers._task_models import TaskCreateBase, TaskUpdateBase
from services import task_service
from services.file_service import tasks_path, write_json

_require_household = require_module("household")

router = APIRouter()

_HOUSEHOLD = "_household"


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


@router.get("")
def list_shared(current_user: dict = Depends(_require_household)):
    _ensure_household()
    return task_service.list_tasks(_HOUSEHOLD)


@router.post("")
def add_shared(req: SharedTaskCreate, current_user: dict = Depends(_require_household)):
    _ensure_household()
    payload = req.model_dump()
    payload["created_by"] = current_user["name"]
    return task_service.add_task(_HOUSEHOLD, payload)


@router.patch("/{task_id}")
def update_shared(task_id: str, req: SharedTaskUpdate, current_user: dict = Depends(_require_household)):
    _validate_task_id(task_id)
    _ensure_household()
    updates = req.model_dump(exclude_unset=True)
    if updates.get("status") in ("done", "skipped"):
        updates["completed_by"] = current_user["name"]
    result = task_service.update_task(_HOUSEHOLD, task_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/{task_id}")
def delete_shared(task_id: str, current_user: dict = Depends(_require_household)):
    _validate_task_id(task_id)
    _ensure_household()
    if not task_service.delete_task(_HOUSEHOLD, task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}
