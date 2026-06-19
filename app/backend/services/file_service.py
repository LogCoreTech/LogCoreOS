"""Generic utilities for reading and writing Brain files (JSON + markdown)."""
import json
import re
from pathlib import Path
from typing import Any

from config import settings

_MISSING = object()


def brain_path() -> Path:
    return settings.brain_path


def user_path(user_name: str) -> Path:
    return brain_path() / "USERS" / user_name


def tasks_path(user_name: str) -> Path:
    return user_path(user_name) / "Tasks" / "tasks.json"


def history_path(user_name: str) -> Path:
    return user_path(user_name) / "Tasks" / "tasks_history.json"


def override_path(user_name: str) -> Path:
    return user_path(user_name) / "Tasks" / "daily_override.json"


def profile_path(user_name: str) -> Path:
    return user_path(user_name) / "Profile.md"


def read_json(path: Path, default: Any = _MISSING) -> Any:
    """Read JSON file.

    If the file is missing and a default is given, returns the default.
    If no default is given and the file is missing, raises FileNotFoundError
    (preserving the original call-site behaviour).
    """
    if not path.exists():
        if default is _MISSING:
            raise FileNotFoundError(path)
        return default
    try:
        with open(path) as f:
            content = f.read().strip()
            if not content:
                return default if default is not _MISSING else {}
            return json.loads(content)
    except (json.JSONDecodeError, OSError):
        if default is not _MISSING:
            return default
        raise


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
        f.write("\n")


def read_markdown(path: Path) -> str:
    with open(path) as f:
        return f.read()


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


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
