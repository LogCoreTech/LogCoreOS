"""Notes module — markdown notes with folder support, stored in Brain/Notes/."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import require_module
from services import notes_service
from services.rate_limiter import rate_limit

_require_notes = require_module("notes")
_write_limit = rate_limit(30, 60)

router = APIRouter()

_MAX_CONTENT = 512_000


class NoteCreate(BaseModel):
    path: str = Field(..., min_length=1, max_length=500)
    content: str = Field(default="", max_length=_MAX_CONTENT)


class NoteUpdate(BaseModel):
    content: str = Field(..., max_length=_MAX_CONTENT)


class FolderCreate(BaseModel):
    path: str = Field(..., min_length=1, max_length=500)


class MoveItem(BaseModel):
    from_path: str = Field(..., min_length=1, max_length=500)
    to_path: str = Field(..., min_length=1, max_length=500)
    type: str = Field(..., pattern="^(note|folder)$")


@router.get("")
def list_notes(current_user: dict = Depends(_require_notes)):
    return notes_service.list_notes(current_user["name"])


@router.get("/file/{path:path}")
def get_note(path: str, current_user: dict = Depends(_require_notes)):
    try:
        note = notes_service.get_note(current_user["name"], path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.post("/file", status_code=201)
def create_note(
    req: NoteCreate,
    current_user: dict = Depends(_require_notes),
    _rl: None = Depends(_write_limit),
):
    try:
        return notes_service.create_note(current_user["name"], req.path, req.content)
    except ValueError as e:
        status = 409 if "already exists" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.put("/file/{path:path}")
def update_note(
    path: str,
    req: NoteUpdate,
    current_user: dict = Depends(_require_notes),
    _rl: None = Depends(_write_limit),
):
    try:
        result = notes_service.update_note(current_user["name"], path, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Note not found")
    return result


@router.delete("/file/{path:path}")
def delete_note(
    path: str,
    current_user: dict = Depends(_require_notes),
    _rl: None = Depends(_write_limit),
):
    try:
        deleted = notes_service.delete_note(current_user["name"], path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}


@router.post("/folder", status_code=201)
def create_folder(
    req: FolderCreate,
    current_user: dict = Depends(_require_notes),
    _rl: None = Depends(_write_limit),
):
    try:
        return notes_service.create_folder(current_user["name"], req.path)
    except ValueError as e:
        status = 409 if "already exists" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.delete("/folder/{path:path}")
def delete_folder(
    path: str,
    current_user: dict = Depends(_require_notes),
    _rl: None = Depends(_write_limit),
):
    try:
        notes_service.delete_folder(current_user["name"], path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/move")
def move_item(
    req: MoveItem,
    current_user: dict = Depends(_require_notes),
    _rl: None = Depends(_write_limit),
):
    try:
        return notes_service.move_item(
            current_user["name"], req.from_path, req.to_path, req.type
        )
    except ValueError as e:
        status = 409 if "already exists" in str(e) else 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status, detail=str(e))
