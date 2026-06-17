import re
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from routers.auth import get_current_user, require_module
from services import task_service, priority_service

_require_tasks = require_module("tasks")

router = APIRouter()


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=50)
    priority: Literal["High", "Medium", "Low"] = "Medium"
    type: Literal["todo", "recurring", "goal", "appointment"] = "todo"
    recurrence: Literal["daily", "weekly", "monthly"] | None = None
    due_date: str | None = None
    due_time: str | None = None  # HH:MM in user's local timezone; stored as UTC when cross-user sharing is added
    notes: str | None = Field(None, max_length=5000)

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise ValueError("due_date must be a valid date in YYYY-MM-DD format")
        return v

    @field_validator("due_time")
    @classmethod
    def validate_due_time(cls, v: str | None) -> str | None:
        if v is not None:
            if not re.match(r"^\d{2}:\d{2}$", v):
                raise ValueError("due_time must be in HH:MM format")
            hh, mm = int(v[:2]), int(v[3:])
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError("due_time must be a valid time (00:00–23:59)")
        return v

    @model_validator(mode='after')
    def due_time_requires_due_date(self):
        if self.due_time and not self.due_date:
            raise ValueError("due_time can only be set when due_date is also provided")
        return self


class TaskUpdate(BaseModel):
    title: str | None = Field(None, max_length=255)
    category: str | None = Field(None, max_length=50)
    priority: Literal["High", "Medium", "Low"] | None = None
    status: Literal["pending", "done", "skipped"] | None = None
    due_date: str | None = None
    due_time: str | None = None
    notes: str | None = Field(None, max_length=5000)

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise ValueError("due_date must be a valid date in YYYY-MM-DD format")
        return v

    @field_validator("due_time")
    @classmethod
    def validate_due_time(cls, v: str | None) -> str | None:
        if v is not None:
            if not re.match(r"^\d{2}:\d{2}$", v):
                raise ValueError("due_time must be in HH:MM format")
            hh, mm = int(v[:2]), int(v[3:])
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError("due_time must be a valid time (00:00–23:59)")
        return v

    @model_validator(mode='after')
    def due_time_requires_due_date(self):
        if self.due_time and not self.due_date:
            raise ValueError("due_time can only be set when due_date is also provided")
        return self


@router.get("")
def list_tasks(current_user: dict = Depends(_require_tasks)):
    return task_service.list_tasks(current_user["name"])


@router.get("/top3")
def top3(current_user: dict = Depends(_require_tasks)):
    return priority_service.get_top3(current_user["name"])


@router.get("/scored")
def all_scored(current_user: dict = Depends(_require_tasks)):
    return priority_service.get_all_scored(current_user["name"])


@router.get("/history")
def history(current_user: dict = Depends(_require_tasks)):
    return task_service.list_history(current_user["name"])


@router.post("")
def add_task(req: TaskCreate, current_user: dict = Depends(_require_tasks)):
    return task_service.add_task(current_user["name"], req.model_dump())


@router.patch("/{task_id}")
def update_task(task_id: str, req: TaskUpdate, current_user: dict = Depends(_require_tasks)):
    # exclude_unset so only fields the client sent are applied;
    # None values are intentional (clearing due_date, notes, etc.)
    updates = req.model_dump(exclude_unset=True)
    result = task_service.update_task(current_user["name"], task_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/{task_id}")
def delete_task(task_id: str, current_user: dict = Depends(_require_tasks)):
    if not task_service.delete_task(current_user["name"], task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}
