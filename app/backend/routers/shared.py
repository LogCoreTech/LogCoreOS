"""Shared household task pool — readable and writable by all authenticated users."""
import re
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from routers.auth import get_current_user, require_module
from services import task_service

_require_household = require_module("household")
from services.file_service import tasks_path, write_json, read_json

router = APIRouter()

_HOUSEHOLD = "_household"


def _ensure_household() -> None:
    """Create the household Tasks dir if it doesn't exist yet."""
    path = tasks_path(_HOUSEHOLD)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, {"tasks": []})


class SharedTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=50)
    priority: Literal["High", "Medium", "Low"] = "Medium"
    type: Literal["todo", "recurring", "goal", "appointment"] = "todo"
    recurrence: Literal["daily", "weekly", "monthly"] | None = None
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


class SharedTaskUpdate(BaseModel):
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
    # Store who created it
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
