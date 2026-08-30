"""CRUD for Journal/YYYY-MM-DD.md files in the user's Brain."""

import re
from pathlib import Path

from services.file_service import read_json, read_markdown, write_json, write_markdown, ws_path

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_CONTENT_BYTES = 512_000


def _validate_date(date: str) -> None:
    if not _DATE_RE.match(date):
        raise ValueError("Date must be YYYY-MM-DD format")


def _journal_root(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "Journal"


def _entry_path(user_name: str, date: str, workspace: str = "personal") -> Path:
    return _journal_root(user_name, workspace) / f"{date}.md"


def list_entries(user_name: str, workspace: str = "personal") -> list[dict]:
    folder = _journal_root(user_name, workspace)
    if not folder.exists():
        return []
    entry_tags = load_entry_tags(user_name, workspace)
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
            entries.append({"date": p.stem, "preview": preview, "tags": entry_tags.get(p.stem, [])})
    return entries


def get_entry(user_name: str, date: str, workspace: str = "personal") -> dict | None:
    _validate_date(date)
    path = _entry_path(user_name, date, workspace)
    if not path.exists():
        return None
    return {"date": date, "content": read_markdown(path), "tags": get_entry_tags(user_name, date, workspace)}


# ---------------------------------------------------------------------------
# Tags (2026-08-29) — a sidecar index, date-keyed, since a journal entry's
# own content has no structured-field mechanism (no frontmatter parsing
# exists anywhere in this codebase) — same shape Notes' own _tags.json
# uses, but genuinely new infrastructure here: unlike Notes, Journal had NO
# JSON store at all before this, not even an existing sidecar to mirror in
# this same file. Stays inside this package (not core) — no external
# consumer of this file exists today.
# ---------------------------------------------------------------------------


def _tags_file(user_name: str, workspace: str = "personal") -> Path:
    return _journal_root(user_name, workspace) / "_tags.json"


def load_entry_tags(user_name: str, workspace: str = "personal") -> dict[str, list[str]]:
    return read_json(_tags_file(user_name, workspace), default={"tags": {}}).get("tags", {})


def get_entry_tags(user_name: str, date: str, workspace: str = "personal") -> list[str]:
    return load_entry_tags(user_name, workspace).get(date, [])


def set_entry_tags(user_name: str, date: str, tags: list[str], workspace: str = "personal") -> list[str]:
    _validate_date(date)
    clean = [t.strip() for t in (tags or []) if isinstance(t, str) and t.strip()]
    current = load_entry_tags(user_name, workspace)
    if clean:
        current[date] = clean
    else:
        current.pop(date, None)
    write_json(_tags_file(user_name, workspace), {"tags": current})
    if clean:
        from services.tags_service import register_tags

        register_tags(user_name, workspace, clean)
    return clean


def upsert_entry(user_name: str, date: str, content: str, workspace: str = "personal") -> dict:
    _validate_date(date)
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        raise ValueError("Entry content exceeds 500 KB limit")
    write_markdown(_entry_path(user_name, date, workspace), content)
    return {"date": date, "content": content}


def delete_entry(user_name: str, date: str, workspace: str = "personal") -> bool:
    _validate_date(date)
    path = _entry_path(user_name, date, workspace)
    if not path.exists():
        return False
    path.unlink()
    set_entry_tags(user_name, date, [], workspace)
    return True
