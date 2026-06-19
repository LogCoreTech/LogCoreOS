"""CRUD for Notes/*.md files in the user's Brain."""
import re
from datetime import datetime
from pathlib import Path

from services.file_service import user_path, read_markdown, write_markdown

_NOTE_RE = re.compile(r'^[\w \-. ]+$')
_MAX_NAME = 100
_MAX_CONTENT_BYTES = 512_000


def _validate_name(name: str) -> None:
    if not name or len(name) > _MAX_NAME or not _NOTE_RE.match(name):
        raise ValueError(
            "Note name must be 1–100 characters: letters, digits, spaces, hyphens, dots, underscores"
        )


def _note_path(user_name: str, name: str) -> Path:
    return user_path(user_name) / "Notes" / f"{name}.md"


def list_notes(user_name: str) -> list[dict]:
    folder = user_path(user_name) / "Notes"
    if not folder.exists():
        return []
    notes = []
    for p in sorted(folder.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file() and p.suffix == ".md":
            notes.append({
                "name": p.stem,
                "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            })
    return notes


def get_note(user_name: str, name: str) -> dict | None:
    _validate_name(name)
    path = _note_path(user_name, name)
    if not path.exists():
        return None
    return {
        "name": name,
        "content": read_markdown(path),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
    }


def create_note(user_name: str, name: str, content: str = "") -> dict:
    _validate_name(name)
    path = _note_path(user_name, name)
    if path.exists():
        raise ValueError(f"A note named {name!r} already exists")
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        raise ValueError("Note content exceeds 500 KB limit")
    write_markdown(path, content)
    return {
        "name": name,
        "content": content,
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
    }


def update_note(user_name: str, name: str, content: str) -> dict | None:
    _validate_name(name)
    path = _note_path(user_name, name)
    if not path.exists():
        return None
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        raise ValueError("Note content exceeds 500 KB limit")
    write_markdown(path, content)
    return {
        "name": name,
        "content": content,
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
    }


def delete_note(user_name: str, name: str) -> bool:
    _validate_name(name)
    path = _note_path(user_name, name)
    if not path.exists():
        return False
    path.unlink()
    return True
