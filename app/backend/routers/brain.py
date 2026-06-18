"""Brain file viewer/editor — read and write the user's personal .md files."""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user, require_module
from services.rate_limiter import rate_limit

_require_brain = require_module("brain")
_brain_write_limit = rate_limit(20, 60)  # 20 writes per minute
from services.file_service import user_path, write_markdown

router = APIRouter()

_MAX_CONTENT_BYTES = 512_000  # 500 KB — more than enough for any markdown file
_ALLOWED_DIRS_SKIP = {"Tasks"}  # managed by tasks module, not editable here


def _list_md(base: Path, rel: str = "") -> list[dict]:
    """Recursively list .md files under base, skipping _ALLOWED_DIRS_SKIP."""
    files = []
    try:
        entries = sorted(base.iterdir(), key=lambda p: (p.is_dir(), p.name))
    except PermissionError:
        return files
    for p in entries:
        rel_path = f"{rel}/{p.name}" if rel else p.name
        if p.is_dir():
            if p.name not in _ALLOWED_DIRS_SKIP:
                files.extend(_list_md(p, rel_path))
        elif p.is_file() and p.suffix == ".md":
            files.append({"path": rel_path, "name": p.name})
    return files


def _resolve(name: str, rel_path: str) -> Path:
    """Resolve rel_path inside user's brain folder; raise on unsafe input."""
    # Reject anything that isn't a safe relative .md path
    parts = rel_path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not rel_path.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are accessible")
    if not all(re.match(r"^[\w\s\-. ]+$", p) for p in parts):
        raise HTTPException(status_code=400, detail="Invalid characters in path")
    if any(p in _ALLOWED_DIRS_SKIP for p in parts[:-1]):
        raise HTTPException(status_code=403, detail="That folder is managed by another module")

    base = user_path(name).resolve()
    target = (user_path(name) / rel_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    return target


@router.get("/files")
def list_files(current_user: dict = Depends(_require_brain)):
    base = user_path(current_user["name"])
    if not base.exists():
        return []
    return _list_md(base)


@router.get("/files/{file_path:path}")
def get_file(file_path: str, current_user: dict = Depends(_require_brain)):
    target = _resolve(current_user["name"], file_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return {"path": file_path, "content": target.read_text()}


class SaveRequest(BaseModel):
    content: str = Field(..., max_length=_MAX_CONTENT_BYTES)


@router.put("/files/{file_path:path}")
def save_file(
    file_path: str,
    req: SaveRequest,
    current_user: dict = Depends(_require_brain),
    _rl: None = Depends(_brain_write_limit),
):
    target = _resolve(current_user["name"], file_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    write_markdown(target, req.content)
    return {"ok": True}
