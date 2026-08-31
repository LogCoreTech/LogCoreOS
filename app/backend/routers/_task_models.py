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


class MonthWeekRule(BaseModel):
    """'Nth weekday of the month' — e.g. ordinal=2, weekday='TU' is 'the 2nd Tuesday'."""

    ordinal: Literal[1, 2, 3, 4, -1]
    weekday: Literal["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


class RecurrenceRule(BaseModel):
    freq: Literal["daily", "weekly", "monthly", "yearly"]
    interval: int = Field(1, ge=1, le=365)
    weekdays: list[Literal["MO", "TU", "WE", "TH", "FR", "SA", "SU"]] | None = None
    month_day: int | None = Field(None, ge=-1, le=31)
    month_week: MonthWeekRule | None = None
    month: int | None = Field(None, ge=1, le=12)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.freq == "weekly":
            if not self.weekdays:
                raise ValueError("weekly recurrence requires at least one weekday")
        elif self.weekdays:
            raise ValueError("weekdays is only valid for weekly recurrence")

        if self.freq in ("monthly", "yearly"):
            if bool(self.month_day is not None) == bool(self.month_week is not None):
                raise ValueError(
                    "monthly/yearly recurrence requires exactly one of month_day or month_week"
                )
            if self.month_day == 0:
                raise ValueError("month_day must be -1 (last day) or 1-31")
        else:
            if self.month_day is not None or self.month_week is not None:
                raise ValueError(
                    "month_day/month_week are only valid for monthly/yearly recurrence"
                )

        if self.freq == "yearly":
            if self.month is None:
                raise ValueError("yearly recurrence requires month")
        elif self.month is not None:
            raise ValueError("month is only valid for yearly recurrence")

        return self


class TaskCreateBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=50)
    priority: Literal["High", "Medium", "Low"] = "Medium"
    type: Literal["todo", "recurring", "appointment"] = "todo"
    recurrence: RecurrenceRule | None = None
    due_date: str | None = None
    due_time: str | None = None
    notes: str | None = Field(None, max_length=5000)
    assigned_to: str | None = None
    asset_id: str | None = Field(None, max_length=64)
    goal_id: str | None = Field(None, max_length=64)
    tags: list[str] | None = None
    counts_toward_goal: bool | None = None

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
    asset_id: str | None = Field(None, max_length=64)
    goal_id: str | None = Field(None, max_length=64)
    tags: list[str] | None = None
    counts_toward_goal: bool | None = None

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
