from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from routers._task_models import TaskCreateBase, TaskUpdateBase
from routers.auth import get_current_user, get_workspace, require_module
from services import priority_service, task_service
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
    return task_service.list_history(
        current_user["name"], limit=limit, offset=offset, workspace=workspace
    )


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
    if not task_service.delete_task(
        current_user["name"], task_id, workspace, deleted_by=current_user["name"]
    ):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}


class BulkDeleteRequest(BaseModel):
    ids: list[str]


@router.post("/bulk-delete")
def bulk_delete_tasks(
    req: BulkDeleteRequest,
    current_user: dict = Depends(_require_tasks),
    workspace: str = Depends(get_workspace),
):
    """UX Polish Batch #4 — bulk-delete always routes through the same
    soft-delete-backed delete_task() the single-item endpoint uses. Personal
    tasks only (this router never resolves pool tasks — Household/Team have
    their own bulk-delete on their own routers if that's ever needed), so no
    per-item access resolution beyond the existing module gate is required."""
    deleted: list[str] = []
    failed: list[dict] = []
    for task_id in req.ids:
        try:
            UUID(task_id)
        except ValueError:
            failed.append({"id": task_id, "error": "Invalid task ID format"})
            continue
        if task_service.delete_task(
            current_user["name"], task_id, workspace, deleted_by=current_user["name"]
        ):
            deleted.append(task_id)
        else:
            failed.append({"id": task_id, "error": "Task not found"})
    return {"deleted": deleted, "failed": failed}
