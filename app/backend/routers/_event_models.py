"""Shared Pydantic models for event create/update — used by calendar.py and shared.py."""

import re
from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

VALID_COLORS = {"orange", "red", "yellow", "green", "teal", "blue", "purple", "pink"}


def _validate_date_str(v: str | None) -> str | None:
    if v is not None:
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("Date must be a valid date in YYYY-MM-DD format")
    return v


def _validate_time_str(v: str | None) -> str | None:
    if v is not None:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("Time must be in HH:MM format")
        hh, mm = int(v[:2]), int(v[3:])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("Time must be a valid time (00:00–23:59)")
    return v


class EventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    start_date: str
    end_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    all_day: bool = True
    color: str = "blue"
    notes: str | None = Field(None, max_length=5000)

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, v: str) -> str:
        return _validate_date_str(v)  # type: ignore[return-value]

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: str | None) -> str | None:
        return _validate_date_str(v)

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, v: str | None) -> str | None:
        return _validate_time_str(v)

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v: str | None) -> str | None:
        return _validate_time_str(v)

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if v not in VALID_COLORS:
            raise ValueError(f"color must be one of: {', '.join(sorted(VALID_COLORS))}")
        return v

    @model_validator(mode="after")
    def check_date_and_time_consistency(self) -> "EventCreate":
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.all_day and (self.start_time or self.end_time):
            raise ValueError("start_time/end_time cannot be set when all_day is True")
        return self


class EventUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    start_date: str | None = None
    end_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    all_day: bool | None = None
    color: str | None = None
    notes: str | None = Field(None, max_length=5000)

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, v: str | None) -> str | None:
        return _validate_date_str(v)

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: str | None) -> str | None:
        return _validate_date_str(v)

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, v: str | None) -> str | None:
        return _validate_time_str(v)

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v: str | None) -> str | None:
        return _validate_time_str(v)

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_COLORS:
            raise ValueError(f"color must be one of: {', '.join(sorted(VALID_COLORS))}")
        return v
