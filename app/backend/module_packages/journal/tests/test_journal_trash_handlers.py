"""Tests for journal/backend/trash_handlers.py — the per-module side of the
trash registry contract (see services/trash_service.py's module docstring
and module_registry.py's trash_dispatch()/owned_trash_types). Journal is the
first module with no JSON payload at all — the whole record is the moved
.md file plus its tags."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.journal.backend import trash_handlers
from module_packages.journal.backend.service import (
    delete_entry,
    get_entry,
    get_entry_tags,
    set_entry_tags,
    upsert_entry,
)
from module_packages.journal.manifest import MODULE
from services import auth_service, mod_store_service

USER = "TestUser"
DATE = "2026-06-20"


@pytest.fixture()
def user_brain(brain):
    mod_store_service.mark_installed("journal", by="test-fixture")
    user_dir = brain / "USERS" / USER / "Journal"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def test_record_types_match_manifest():
    assert trash_handlers.RECORD_TYPES == MODULE.owned_trash_types


def test_describe_uses_date():
    title, subtitle = trash_handlers.describe("journal_entry", {"date": DATE})
    assert title == f"Journal entry — {DATE}"
    assert subtitle == "Journal"


def test_restore_moves_file_and_tags_back(user_brain):
    upsert_entry(USER, DATE, "Dear diary...")
    set_entry_tags(USER, DATE, ["gratitude"])

    delete_entry(USER, DATE, deleted_by=USER)
    assert get_entry(USER, DATE) is None
    assert get_entry_tags(USER, DATE) == []

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    entry = next(e for e in entries if e["original_id"] == DATE)

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["date"] == DATE
    assert restored["content"] == "Dear diary..."

    got = get_entry(USER, DATE)
    assert got is not None
    assert got["content"] == "Dear diary..."
    assert got["tags"] == ["gratitude"]


def test_restore_conflict_raises_when_entry_already_exists(user_brain):
    upsert_entry(USER, DATE, "Original")
    delete_entry(USER, DATE, deleted_by=USER)

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    entry = next(e for e in entries if e["original_id"] == DATE)

    upsert_entry(USER, DATE, "A new entry written before the restore")

    with pytest.raises(ValueError):
        trash_handlers.restore(USER, "personal", entry)


def test_access_check_always_true():
    assert trash_handlers.access_check({"name": USER}, "personal", {}) is True
