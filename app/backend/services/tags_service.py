"""Shared tag vocabulary for Goals + Tasks. Stays core (not inside
module_packages/goals/) since both Goals' package and core task_service.py
need it — the same "real external consumer keeps it core" test every prior
service decision in this project has used. One vocabulary per store
(personal or pool), so a tag means the same thing whether it's on a goal or
a task, and personal/pool tags stay separate the same way pool priorities
already are.

Deliberately a real, persisted, growing list — not live-scanned from
existing records — so the picker's suggestions reflect every tag ever used,
even after the last record carrying it is deleted (matches how the owner
described wanting search/autocomplete to behave)."""

from services.file_service import read_json, tags_path, update_json

_TAG_MAX_LEN = 30
_VOCAB_CAP = 500  # generous ceiling against unbounded growth; not a realistic limit in practice


def get_tags(store_user: str, workspace: str = "personal") -> list[str]:
    return read_json(tags_path(store_user, workspace), default={"tags": []}).get("tags", [])


def register_tags(store_user: str, workspace: str, tags: list[str]) -> list[str]:
    """Union-add any new tags into the store's vocabulary; returns the full
    updated list. Case-preserving but de-duplicates case-insensitively (the
    first-seen casing wins), same convention TagInput's own `strict` mode
    already uses for canonical-value matching."""
    clean = [t.strip()[:_TAG_MAX_LEN] for t in tags if t and t.strip()]
    if not clean:
        return get_tags(store_user, workspace)

    def _update(data: dict) -> dict:
        existing = data.get("tags", [])
        lower_existing = {t.lower() for t in existing}
        for t in clean:
            if t.lower() not in lower_existing:
                existing.append(t)
                lower_existing.add(t.lower())
        data["tags"] = existing[:_VOCAB_CAP]
        return data

    result = update_json(tags_path(store_user, workspace), _update, default={"tags": []})
    return result["tags"]
