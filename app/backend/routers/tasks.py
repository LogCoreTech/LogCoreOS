from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.auth import get_current_user
from services import task_service, priority_service

router = APIRouter()


class TaskCreate(BaseModel):
    title: str
    category: str = ""
    priority: str = "Medium"
    type: str = "todo"
    recurrence: str | None = None
    due_date: str | None = None
    notes: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    priority: str | None = None
    status: str | None = None
    due_date: str | None = None
    notes: str | None = None


@router.get("")
def list_tasks(current_user: dict = Depends(get_current_user)):
    return task_service.list_tasks(current_user["name"])


@router.get("/top3")
def top3(current_user: dict = Depends(get_current_user)):
    return priority_service.get_top3(current_user["name"])


@router.get("/scored")
def all_scored(current_user: dict = Depends(get_current_user)):
    return priority_service.get_all_scored(current_user["name"])


@router.get("/history")
def history(current_user: dict = Depends(get_current_user)):
    return task_service.list_history(current_user["name"])


@router.post("")
def add_task(req: TaskCreate, current_user: dict = Depends(get_current_user)):
    return task_service.add_task(current_user["name"], req.model_dump())


@router.patch("/{task_id}")
def update_task(task_id: str, req: TaskUpdate, current_user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = task_service.update_task(current_user["name"], task_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/{task_id}")
def delete_task(task_id: str, current_user: dict = Depends(get_current_user)):
    if not task_service.delete_task(current_user["name"], task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}
