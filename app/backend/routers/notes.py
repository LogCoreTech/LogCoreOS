"""Notes module — markdown notes stored in Brain/Notes/."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import require_module
from services import notes_service
from services.rate_limiter import rate_limit

_require_notes = require_module("notes")
_write_limit = rate_limit(30, 60)

router = APIRouter()

_MAX_CONTENT = 512_000
_NAME_RE = re.compile(r'^[\w \-. ]+$')


def _check_name(name: str) -> str:
    if not name or len(name) > 100 or not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid note name")
    return name


class NoteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(default="", max_length=_MAX_CONTENT)


class NoteUpdate(BaseModel):
    content: str = Field(..., max_length=_MAX_CONTENT)


@router.get("")
def list_notes(current_user: dict = Depends(_require_notes)):
    return notes_service.list_notes(current_user["name"])


@router.get("/{name}")
def get_note(name: str, current_user: dict = Depends(_require_notes)):
    _check_name(name)
    note = notes_service.get_note(current_user["name"], name)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.post("", status_code=201)
def create_note(
    req: NoteCreate,
    current_user: dict = Depends(_require_notes),
    _rl: None = Depends(_write_limit),
):
    try:
        return notes_service.create_note(current_user["name"], req.name, req.content)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/{name}")
def update_note(
    name: str,
    req: NoteUpdate,
    current_user: dict = Depends(_require_notes),
    _rl: None = Depends(_write_limit),
):
    _check_name(name)
    try:
        result = notes_service.update_note(current_user["name"], name, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Note not found")
    return result


@router.delete("/{name}")
def delete_note(
    name: str,
    current_user: dict = Depends(_require_notes),
    _rl: None = Depends(_write_limit),
):
    _check_name(name)
    if not notes_service.delete_note(current_user["name"], name):
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}
