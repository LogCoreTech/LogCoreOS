"""Brain file viewer/editor — read and write the user's personal .md files."""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user, get_workspace
from services.rate_limiter import rate_limit

_brain_write_limit = rate_limit(20, 60)  # 20 writes per minute
from services.file_service import ws_path, write_markdown

router = APIRouter()

_MAX_CONTENT_BYTES = 512_000  # 500 KB — more than enough for any markdown file
_ALLOWED_DIRS_SKIP = {
    "Tasks",  # managed by tasks module, not editable here
    # ws_path()'s "business" base is a literal subfolder of the "personal" base
    # (brain/USERS/{name}/Business/), not a sibling — so a plain recursive walk
    # or path resolution against the personal base would otherwise reach straight
    # into the other workspace's files. Reusing the same skip mechanism blocks
    # both the listing leak and a path-traversal read/write across the boundary
    # (a personal-workspace request for "Business/<file>.md" would resolve to
    # a real file that DOES exist without this, since it's genuinely nested
    # inside the personal base on disk).
    "Business",
}


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


def _resolve(name: str, workspace: str, rel_path: str) -> Path:
    """Resolve rel_path inside user's workspace-scoped brain folder; raise on unsafe input."""
    # Reject anything that isn't a safe relative .md path
    parts = rel_path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not rel_path.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are accessible")
    if not all(re.match(r"^[\w \-. ]+$", p) for p in parts):
        raise HTTPException(status_code=400, detail="Invalid characters in path")
    if any(p in _ALLOWED_DIRS_SKIP for p in parts[:-1]):
        raise HTTPException(status_code=403, detail="That folder is managed by another module")

    base = ws_path(name, workspace).resolve()
    target = (ws_path(name, workspace) / rel_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    return target


@router.get("/files")
def list_files(
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    base = ws_path(current_user["name"], workspace)
    if not base.exists():
        return []
    return _list_md(base)


@router.get("/files/{file_path:path}")
def get_file(
    file_path: str,
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    target = _resolve(current_user["name"], workspace, file_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return {"path": file_path, "content": target.read_text()}


class SaveRequest(BaseModel):
    content: str = Field(..., max_length=_MAX_CONTENT_BYTES)


@router.put("/files/{file_path:path}")
def save_file(
    file_path: str,
    req: SaveRequest,
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_brain_write_limit),
):
    target = _resolve(current_user["name"], workspace, file_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    write_markdown(target, req.content)
    return {"ok": True}
