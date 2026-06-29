"""CRUD for Journal/YYYY-MM-DD.md files in the user's Brain."""
import re
from pathlib import Path

from services.file_service import user_path, read_markdown, write_markdown

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_MAX_CONTENT_BYTES = 512_000


def _validate_date(date: str) -> None:
    if not _DATE_RE.match(date):
        raise ValueError("Date must be YYYY-MM-DD format")


def _entry_path(user_name: str, date: str) -> Path:
    return user_path(user_name) / "Journal" / f"{date}.md"


def list_entries(user_name: str) -> list[dict]:
    folder = user_path(user_name) / "Journal"
    if not folder.exists():
        return []
    entries = []
    for p in sorted(folder.iterdir(), key=lambda x: x.name, reverse=True):
        if p.is_file() and p.suffix == ".md" and _DATE_RE.match(p.stem):
            preview = ""
            try:
                for line in p.read_text().splitlines():
                    stripped = line.strip()
                    if stripped:
                        preview = stripped[:100]
                        break
            except OSError:
                pass
            entries.append({"date": p.stem, "preview": preview})
    return entries


def get_entry(user_name: str, date: str) -> dict | None:
    _validate_date(date)
    path = _entry_path(user_name, date)
    if not path.exists():
        return None
    return {"date": date, "content": read_markdown(path)}


def upsert_entry(user_name: str, date: str, content: str) -> dict:
    _validate_date(date)
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        raise ValueError("Entry content exceeds 500 KB limit")
    write_markdown(_entry_path(user_name, date), content)
    return {"date": date, "content": content}


def delete_entry(user_name: str, date: str) -> bool:
    _validate_date(date)
    path = _entry_path(user_name, date)
    if not path.exists():
        return False
    path.unlink()
    return True
