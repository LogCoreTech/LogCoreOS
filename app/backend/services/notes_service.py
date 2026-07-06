"""CRUD for Notes/ files and folders in the user's Brain."""

import re
import shutil
from datetime import datetime
from pathlib import Path

from services.file_service import read_markdown, write_markdown, ws_path

_SEGMENT_RE = re.compile(r"^[\w \-. ]+$")
_MAX_CONTENT_BYTES = 512_000

_GETTING_STARTED_PATH = "Getting Started"
_GETTING_STARTED_CONTENT = """# Welcome to Notes

Use the sidebar to create and organize your notes.

## Navigation

- **+ Note** — create a new note (inside the selected folder, or at the root if none selected)
- **+ Folder** — create a folder to organize notes
- Click a folder to open/close it; click it again to deselect it so new notes go to the root
- Hover any note or folder and click **···** for rename, move, or delete options

## Tips

- Notes auto-save as you type — no save button needed
- Your notes are stored as plain Markdown files in your Brain folder
- You can access and edit them from any AI tool that reads your Brain
"""


def _validate_path(path: str) -> None:
    parts = path.split("/")
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise ValueError("Invalid path")
    if not all(_SEGMENT_RE.match(p) for p in parts):
        raise ValueError(
            "Path contains invalid characters (use letters, digits, spaces, hyphens, dots, underscores)"
        )


def _notes_root(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "Notes"


def _note_path(user_name: str, path: str, workspace: str = "personal") -> Path:
    return _notes_root(user_name, workspace) / f"{path}.md"


def _folder_path(user_name: str, path: str, workspace: str = "personal") -> Path:
    return _notes_root(user_name, workspace) / path


def list_notes(user_name: str, workspace: str = "personal") -> list[dict]:
    """Return a flat list of all notes and folders (recursive) for tree-building."""
    root = _notes_root(user_name, workspace)
    if not root.exists():
        return []
    items: list[dict] = []

    def _walk(dir_path: Path, rel: str) -> None:
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return
        for p in entries:
            p_rel = f"{rel}/{p.name}" if rel else p.name
            if p.is_dir():
                items.append({"type": "folder", "path": p_rel, "name": p.name})
                _walk(p, p_rel)
            elif p.is_file() and p.suffix == ".md":
                note_rel = f"{rel}/{p.stem}" if rel else p.stem
                items.append(
                    {
                        "type": "note",
                        "path": note_rel,
                        "name": p.stem,
                        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                    }
                )

    _walk(root, "")

    # Create a Getting Started note for first-time users (no notes exist yet)
    if not any(i["type"] == "note" for i in items):
        p = _note_path(user_name, _GETTING_STARTED_PATH, workspace)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_GETTING_STARTED_CONTENT, encoding="utf-8")
        items.append(
            {
                "type": "note",
                "path": _GETTING_STARTED_PATH,
                "name": "Getting Started",
                "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            }
        )

    return items


def get_note(user_name: str, path: str, workspace: str = "personal") -> dict | None:
    _validate_path(path)
    p = _note_path(user_name, path, workspace)
    if not p.exists():
        return None
    return {
        "path": path,
        "name": Path(path).name,
        "content": read_markdown(p),
        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


def create_note(user_name: str, path: str, content: str = "", workspace: str = "personal") -> dict:
    _validate_path(path)
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        raise ValueError("Content exceeds 500 KB limit")
    p = _note_path(user_name, path, workspace)
    if p.exists():
        raise ValueError(f"A note already exists at {path!r}")
    write_markdown(p, content)
    return {
        "path": path,
        "name": Path(path).name,
        "content": content,
        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


def update_note(
    user_name: str, path: str, content: str, workspace: str = "personal"
) -> dict | None:
    _validate_path(path)
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        raise ValueError("Content exceeds 500 KB limit")
    p = _note_path(user_name, path, workspace)
    if not p.exists():
        return None
    write_markdown(p, content)
    return {
        "path": path,
        "name": Path(path).name,
        "content": content,
        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


def delete_note(user_name: str, path: str, workspace: str = "personal") -> bool:
    _validate_path(path)
    p = _note_path(user_name, path, workspace)
    if not p.exists():
        return False
    p.unlink()
    return True


def create_folder(user_name: str, path: str, workspace: str = "personal") -> dict:
    _validate_path(path)
    p = _folder_path(user_name, path, workspace)
    if p.exists():
        raise ValueError(f"A folder already exists at {path!r}")
    p.mkdir(parents=True)
    return {"type": "folder", "path": path, "name": Path(path).name}


def delete_folder(user_name: str, path: str, workspace: str = "personal") -> bool:
    _validate_path(path)
    p = _folder_path(user_name, path, workspace)
    if not p.exists() or not p.is_dir():
        return False
    shutil.rmtree(p)
    return True


def move_item(
    user_name: str, from_path: str, to_path: str, item_type: str, workspace: str = "personal"
) -> dict:
    """Rename or move a note or folder."""
    _validate_path(from_path)
    _validate_path(to_path)
    root = _notes_root(user_name, workspace)
    if item_type == "note":
        src = root / f"{from_path}.md"
        dst = root / f"{to_path}.md"
    else:
        src = root / from_path
        dst = root / to_path
    if not src.exists():
        raise ValueError(f"Source not found: {from_path!r}")
    if dst.exists():
        raise ValueError(f"Destination already exists: {to_path!r}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return {"from_path": from_path, "to_path": to_path, "type": item_type}
