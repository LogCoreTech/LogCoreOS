"""Generic utilities for reading and writing Brain files (JSON + markdown)."""

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from config import settings

# In-process lock per file path — safe for single-worker uvicorn
_path_locks: dict[str, threading.Lock] = {}
_path_locks_mutex = threading.Lock()


def _get_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _path_locks_mutex:
        if key not in _path_locks:
            _path_locks[key] = threading.Lock()
        return _path_locks[key]


def brain_path() -> Path:
    return settings.brain_path


def user_path(user_name: str) -> Path:
    return brain_path() / "USERS" / user_name


def ws_path(user_name: str, workspace: str = "personal") -> Path:
    """Return the workspace-scoped base path for a user.

    "personal" → brain/USERS/{name}/   (unchanged paths — backward compat)
    "business"  → brain/USERS/{name}/Business/
    Pseudo-users like _household/_team always use the "personal" base.
    """
    base = user_path(user_name)
    return base if workspace == "personal" else base / "Business"


def tasks_path(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "Tasks" / "tasks.json"


def history_path(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "Tasks" / "tasks_history.json"


def override_path(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "Tasks" / "daily_override.json"


def events_path(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "Calendar" / "events.json"


def assets_path(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "Assets" / "assets.json"


def assets_files_path(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "Assets" / "files"


def asset_templates_path() -> Path:
    return brain_path() / "_system" / "asset_templates.json"


def personal_templates_path(user_name: str) -> Path:
    # Per-user (workspace-agnostic) template store — a user's templates are usable
    # in both their workspaces.
    return user_path(user_name) / "Assets" / "templates.json"


def automations_path(user_name: str) -> Path:
    return user_path(user_name) / "Automations" / "workflows.json"


def system_automations_path() -> Path:
    return brain_path() / "_system" / "automations_index.json"


def automation_inbox_path(user_name: str) -> Path:
    """Inbox store for workflow-written reviewable items. user_name is a real
    user (personal scope) or the _team pool pseudo-user (business scope)."""
    return user_path(user_name) / "Automations" / "inbox.json"


def profile_path(user_name: str) -> Path:
    return user_path(user_name) / "Profile.md"


def read_json(path: Path, default: Any = None) -> Any:
    """Read JSON file; return default (or {}) if missing or empty."""
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path) as f:
            content = f.read().strip()
            return json.loads(content) if content else (default if default is not None else {})
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


def write_json(path: Path, data: Any) -> None:
    """Atomic write with in-process locking — prevents partial reads during writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _get_lock(path)
    with lock:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, default=str)
                f.write("\n")
            os.replace(tmp, path)  # atomic on POSIX
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def read_markdown(path: Path) -> str:
    with open(path) as f:
        return f.read()


def write_markdown(path: Path, content: str) -> None:
    """Atomic write for markdown files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _get_lock(path)
    with lock:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def resolve_user_md_path(user_name: str, rel_path: str) -> Path:
    """Resolve rel_path inside user's brain folder; raise ValueError on unsafe input.

    Enforces: .md extension only, no path traversal, safe characters.
    Does NOT check if the file exists — callers handle that.
    """
    parts = rel_path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"Invalid path: {rel_path!r}")
    if not rel_path.endswith(".md"):
        raise ValueError("Only .md files are accessible")
    if not all(re.match(r"^[\w \-. ]+$", p) for p in parts):
        raise ValueError(f"Invalid characters in path: {rel_path!r}")

    base = user_path(user_name).resolve()
    target = (user_path(user_name) / rel_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(f"Access denied: {rel_path!r}")
    return target


def parse_priority_order(user_name: str) -> list[str]:
    """Extract ordered priority categories from Profile.md."""
    profile = read_markdown(profile_path(user_name))
    in_section = False
    order = []
    for line in profile.splitlines():
        if line.strip() == "## Life Priorities":
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            match = re.match(r"^\d+\.\s+(.+)$", line.strip())
            if match:
                order.append(match.group(1).strip())
    return order
