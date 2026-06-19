"""CRUD for Notes/ files and folders in the user's Brain."""
import re
import shutil
from datetime import datetime
from pathlib import Path

from services.file_service import user_path, read_markdown, write_markdown

_SEGMENT_RE = re.compile(r'^[\w \-. ]+$')
_MAX_CONTENT_BYTES = 512_000


def _validate_path(path: str) -> None:
    parts = path.split("/")
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise ValueError("Invalid path")
    if not all(_SEGMENT_RE.match(p) for p in parts):
        raise ValueError("Path contains invalid characters (use letters, digits, spaces, hyphens, dots, underscores)")


def _notes_root(user_name: str) -> Path:
    return user_path(user_name) / "Notes"


def _note_path(user_name: str, path: str) -> Path:
    return _notes_root(user_name) / f"{path}.md"


def _folder_path(user_name: str, path: str) -> Path:
    return _notes_root(user_name) / path


def list_notes(user_name: str) -> list[dict]:
    """Return a flat list of all notes and folders (recursive) for tree-building."""
    root = _notes_root(user_name)
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
                items.append({
                    "type": "note",
                    "path": note_rel,
                    "name": p.stem,
                    "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                })

    _walk(root, "")
    return items


def get_note(user_name: str, path: str) -> dict | None:
    _validate_path(path)
    p = _note_path(user_name, path)
    if not p.exists():
        return None
    return {
        "path": path,
        "name": Path(path).name,
        "content": read_markdown(p),
        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


def create_note(user_name: str, path: str, content: str = "") -> dict:
    _validate_path(path)
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        raise ValueError("Content exceeds 500 KB limit")
    p = _note_path(user_name, path)
    if p.exists():
        raise ValueError(f"A note already exists at {path!r}")
    write_markdown(p, content)  # write_markdown creates parent dirs
    return {
        "path": path,
        "name": Path(path).name,
        "content": content,
        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


def update_note(user_name: str, path: str, content: str) -> dict | None:
    _validate_path(path)
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        raise ValueError("Content exceeds 500 KB limit")
    p = _note_path(user_name, path)
    if not p.exists():
        return None
    write_markdown(p, content)
    return {
        "path": path,
        "name": Path(path).name,
        "content": content,
        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


def delete_note(user_name: str, path: str) -> bool:
    _validate_path(path)
    p = _note_path(user_name, path)
    if not p.exists():
        return False
    p.unlink()
    return True


def create_folder(user_name: str, path: str) -> dict:
    _validate_path(path)
    p = _folder_path(user_name, path)
    if p.exists():
        raise ValueError(f"A folder already exists at {path!r}")
    p.mkdir(parents=True)
    return {"type": "folder", "path": path, "name": Path(path).name}


def delete_folder(user_name: str, path: str) -> bool:
    _validate_path(path)
    p = _folder_path(user_name, path)
    if not p.exists() or not p.is_dir():
        return False
    shutil.rmtree(p)
    return True


def move_item(user_name: str, from_path: str, to_path: str, item_type: str) -> dict:
    """Rename or move a note or folder."""
    _validate_path(from_path)
    _validate_path(to_path)
    root = _notes_root(user_name)
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
