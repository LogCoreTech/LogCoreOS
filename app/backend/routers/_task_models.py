"""Shared Pydantic models for task create/update — used by tasks.py and shared.py."""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _validate_due_date_value(v: str | None) -> str | None:
    if v is not None:
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("due_date must be a valid date in YYYY-MM-DD format")
    return v


def _validate_due_time_value(v: str | None) -> str | None:
    if v is not None:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("due_time must be in HH:MM format")
        hh, mm = int(v[:2]), int(v[3:])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("due_time must be a valid time (00:00–23:59)")
    return v


class TaskCreateBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=50)
    priority: Literal["High", "Medium", "Low"] = "Medium"
    type: Literal["todo", "recurring", "goal", "appointment"] = "todo"
    recurrence: Literal["daily", "weekly", "monthly"] | None = None
    due_date: str | None = None
    due_time: str | None = None
    notes: str | None = Field(None, max_length=5000)
    assigned_to: str | None = None

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v: str | None) -> str | None:
        return _validate_due_date_value(v)

    @field_validator("due_time")
    @classmethod
    def validate_due_time(cls, v: str | None) -> str | None:
        return _validate_due_time_value(v)

    @model_validator(mode="after")
    def due_time_requires_due_date(self):
        if self.due_time and not self.due_date:
            raise ValueError("due_time can only be set when due_date is also provided")
        return self


class TaskUpdateBase(BaseModel):
    title: str | None = Field(None, max_length=255)
    category: str | None = Field(None, max_length=50)
    priority: Literal["High", "Medium", "Low"] | None = None
    status: Literal["pending", "done", "skipped"] | None = None
    due_date: str | None = None
    due_time: str | None = None
    notes: str | None = Field(None, max_length=5000)
    assigned_to: str | None = None

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v: str | None) -> str | None:
        return _validate_due_date_value(v)

    @field_validator("due_time")
    @classmethod
    def validate_due_time(cls, v: str | None) -> str | None:
        return _validate_due_time_value(v)

    @model_validator(mode="after")
    def due_time_requires_due_date(self):
        if self.due_time and not self.due_date:
            raise ValueError("due_time can only be set when due_date is also provided")
        return self
