"""Journal module — daily entries stored as YYYY-MM-DD.md in Brain/Journal/."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import require_module
from services import journal_service
from services.rate_limiter import rate_limit

_require_journal = require_module("journal")
_write_limit = rate_limit(30, 60)

router = APIRouter()

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_MAX_CONTENT = 512_000


def _check_date(date: str) -> str:
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")
    return date


class EntryUpsert(BaseModel):
    content: str = Field(..., max_length=_MAX_CONTENT)


@router.get("")
def list_entries(current_user: dict = Depends(_require_journal)):
    return journal_service.list_entries(current_user["name"])


@router.get("/{date}")
def get_entry(date: str, current_user: dict = Depends(_require_journal)):
    _check_date(date)
    entry = journal_service.get_entry(current_user["name"], date)
    return entry if entry else {"date": date, "content": ""}


@router.put("/{date}")
def upsert_entry(
    date: str,
    req: EntryUpsert,
    current_user: dict = Depends(_require_journal),
    _rl: None = Depends(_write_limit),
):
    _check_date(date)
    try:
        return journal_service.upsert_entry(current_user["name"], date, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{date}")
def delete_entry(
    date: str,
    current_user: dict = Depends(_require_journal),
    _rl: None = Depends(_write_limit),
):
    _check_date(date)
    if not journal_service.delete_entry(current_user["name"], date):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"ok": True}
