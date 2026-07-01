from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from routers.auth import get_current_user, get_workspace, require_module
from routers._task_models import TaskCreateBase, TaskUpdateBase
from services import task_service, priority_service
from services.file_service import read_json, tasks_path

_require_tasks = require_module("tasks")

router = APIRouter()


class TaskCreate(TaskCreateBase):
    pass


class TaskUpdate(TaskUpdateBase):
    pass


@router.get("")
def list_tasks(
    current_user: dict = Depends(_require_tasks),
    workspace: str = Depends(get_workspace),
):
    return task_service.list_tasks(current_user["name"], workspace)


@router.get("/top3")
def top3(
    current_user: dict = Depends(_require_tasks),
    workspace: str = Depends(get_workspace),
):
    return priority_service.get_top3(current_user["name"], workspace)


@router.get("/scored")
def all_scored(
    current_user: dict = Depends(_require_tasks),
    workspace: str = Depends(get_workspace),
):
    return priority_service.get_all_scored(current_user["name"], workspace)


@router.get("/assigned")
def assigned_tasks(
    current_user: dict = Depends(_require_tasks),
    workspace: str = Depends(get_workspace),
):
    """Return pool tasks assigned to the current user.

    Personal workspace → Household pool tasks assigned to this user.
    Business workspace → Team pool tasks assigned to this user.
    """
    user_name = current_user["name"]
    if workspace == "business":
        pool, source = "_team", "team"
    else:
        pool, source = "_household", "household"

    all_tasks = read_json(tasks_path(pool), default={"tasks": []}).get("tasks", [])
    assigned = [
        {**t, "_source": source}
        for t in all_tasks
        if t.get("assigned_to") == user_name and t.get("status") == "pending"
    ]
    return assigned


@router.get("/history")
def history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(_require_tasks),
    workspace: str = Depends(get_workspace),
):
    return task_service.list_history(current_user["name"], limit=limit, offset=offset, workspace=workspace)


@router.post("")
def add_task(
    req: TaskCreate,
    current_user: dict = Depends(_require_tasks),
    workspace: str = Depends(get_workspace),
):
    return task_service.add_task(current_user["name"], req.model_dump(), workspace)


def _validate_task_id(task_id: str) -> str:
    try:
        UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    return task_id


@router.patch("/{task_id}")
def update_task(
    task_id: str,
    req: TaskUpdate,
    current_user: dict = Depends(_require_tasks),
    workspace: str = Depends(get_workspace),
):
    _validate_task_id(task_id)
    updates = req.model_dump(exclude_unset=True)
    result = task_service.update_task(current_user["name"], task_id, updates, workspace)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    current_user: dict = Depends(_require_tasks),
    workspace: str = Depends(get_workspace),
):
    _validate_task_id(task_id)
    if not task_service.delete_task(current_user["name"], task_id, workspace):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}
