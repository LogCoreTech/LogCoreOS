"""Brain file viewer/editor — read and write the user's personal .md files."""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user, get_workspace
from services.rate_limiter import rate_limit

_brain_write_limit = rate_limit(20, 60)  # 20 writes per minute
from services.file_service import write_markdown, ws_path

router = APIRouter()

_MAX_CONTENT_BYTES = 512_000  # 500 KB — more than enough for any markdown file
_ALWAYS_SKIP = {
    "Tasks",  # managed by tasks module, not editable here
    "Dashboards",  # managed by dashboard module, JSON not markdown, not editable here
    "Assets",  # managed by assets module, JSON + binary attachment files, not editable here
    "Contacts",  # managed by contacts module, JSON + binary photo files, not editable here
    "Finance",  # managed by finance module, JSON + binary receipt files, not editable here
    "Goals",  # managed by goals module, JSON not markdown, not editable here
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


def _skip_dirs(disabled_modules: set[str]) -> set[str]:
    """_ALWAYS_SKIP plus the owned_brain_paths of every module DISABLED for
    this particular user.

    Per-user, not instance-wide: a module can be installed instance-wide and
    still disabled for one role/user (feature-role toggle or a per-user
    override), and that case must hide its folder here too — not just the
    "never installed at all" case. This matches how every other real
    markdown module (Notes, etc.) already works: dual-accessible (dedicated
    UI + this raw browser) when enabled, hidden here only when disabled.
    Tasks/Dashboards/Assets/Contacts/Finance/Goals/Business are the
    pre-existing exceptions, skipped regardless of any toggle because
    they're structurally different (Tasks/Dashboards/Assets/Contacts/
    Finance/Goals are JSON (+ binary files for Assets/Contacts/Finance),
    not markdown; Business is a nested workspace root), not
    module-disabled semantics.
    """
    from module_registry import brain_paths_for_disabled

    return _ALWAYS_SKIP | brain_paths_for_disabled(disabled_modules)


def _list_md(base: Path, disabled_modules: set[str], rel: str = "") -> list[dict]:
    """Recursively list .md files under base, skipping _skip_dirs()."""
    files = []
    skip = _skip_dirs(disabled_modules)
    try:
        entries = sorted(base.iterdir(), key=lambda p: (p.is_dir(), p.name))
    except PermissionError:
        return files
    for p in entries:
        rel_path = f"{rel}/{p.name}" if rel else p.name
        if p.is_dir():
            if p.name not in skip:
                files.extend(_list_md(p, disabled_modules, rel_path))
        elif p.is_file() and p.suffix == ".md":
            files.append({"path": rel_path, "name": p.name})
    return files


def _resolve(name: str, workspace: str, rel_path: str, disabled_modules: set[str]) -> Path:
    """Resolve rel_path inside user's workspace-scoped brain folder; raise on unsafe input."""
    # Reject anything that isn't a safe relative .md path
    parts = rel_path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not rel_path.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are accessible")
    if not all(re.match(r"^[\w \-. ]+$", p) for p in parts):
        raise HTTPException(status_code=400, detail="Invalid characters in path")
    if any(p in _skip_dirs(disabled_modules) for p in parts[:-1]):
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
    return _list_md(base, set(current_user.get("disabled_modules", [])))


@router.get("/files/{file_path:path}")
def get_file(
    file_path: str,
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    target = _resolve(
        current_user["name"], workspace, file_path, set(current_user.get("disabled_modules", []))
    )
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
    target = _resolve(
        current_user["name"], workspace, file_path, set(current_user.get("disabled_modules", []))
    )
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    write_markdown(target, req.content)
    return {"ok": True}
