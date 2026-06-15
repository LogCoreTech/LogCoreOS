"""Generic utilities for reading and writing Brain files (JSON + markdown)."""
import json
import re
from pathlib import Path
from typing import Any

from config import settings


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


def read_json(path: Path) -> Any:
    with open(path) as f:
        return json.load(f)


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
