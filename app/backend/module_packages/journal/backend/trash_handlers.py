"""Trash registry contract for the journal module — see module_registry.py's
trash_dispatch()/owned_trash_types and services/trash_service.py's module
docstring for the shared per-module contract. A journal entry has no JSON
payload — the whole record IS the moved .md file, plus its tags (no
independent JSON store existed for tags before soft-delete either, so they
ride along in `original_location` rather than `payload`).
"""

from module_packages.journal.backend.service import _entry_path, set_entry_tags
from services.file_service import ws_path

RECORD_TYPES = ["journal_entry"]


def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    date = (payload or {}).get("date", "?")
    return f"Journal entry — {date}", "Journal"


def restore(store_user: str, workspace: str, entry: dict) -> dict:
    date = entry["original_id"]
    dest = _entry_path(store_user, date, workspace)
    if dest.exists():
        raise ValueError(
            "A journal entry already exists for this date — it may have already been restored."
        )

    file_ref = entry.get("file_ref")
    if not file_ref:
        raise ValueError("Trash entry is missing its file reference")
    src = ws_path(store_user, workspace) / file_ref
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dest)

    tags = (entry.get("original_location") or {}).get("tags") or []
    if tags:
        set_entry_tags(store_user, date, tags, workspace)

    return {"date": date, "content": dest.read_text()}


def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """Journal is hardcoded never-shareable anywhere in this app (no pool
    store, no per-item sharing) — list_trash_for_user() only ever reads a
    journal entry from the caller's own store, so every entry that reaches
    this point is already visible to `user`."""
    return True
