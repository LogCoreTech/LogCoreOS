"""Tests for notes/backend/trash_handlers.py — the per-module side of the
trash registry contract (see services/trash_service.py's module docstring
and module_registry.py's trash_dispatch()/owned_trash_types). Notes is the
first module with two distinct record types (note, folder), both file/
directory moves with no JSON payload."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.notes.backend import trash_handlers
from module_packages.notes.manifest import MODULE
from services import auth_service, mod_store_service
from services.notes_service import (
    create_folder,
    create_note,
    delete_folder,
    delete_note,
    get_note,
    set_note_tags,
)

USER = "TestUser"


@pytest.fixture()
def user_brain(brain):
    mod_store_service.mark_installed("notes", by="test-fixture")
    user_dir = brain / "USERS" / USER / "Notes"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def test_record_types_match_manifest():
    assert trash_handlers.RECORD_TYPES == MODULE.owned_trash_types


def test_describe_note_and_folder():
    title, subtitle = trash_handlers.describe("note", {"path": "Work/Ideas"})
    assert title == "Ideas"
    assert subtitle == "Notes · Work/Ideas"

    title, subtitle = trash_handlers.describe("folder", {"path": "Work"})
    assert title == "Work"
    assert subtitle == "Notes folder · Work"


def test_restore_note_brings_back_content_and_tags(user_brain):
    create_note(USER, "MyNote", "Hello there")
    set_note_tags(USER, "personal", "MyNote", ["important"])

    delete_note(USER, "MyNote", "personal", deleted_by=USER)
    assert get_note(USER, "MyNote") is None

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    entry = next(e for e in entries if e["original_id"] == "MyNote")

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["content"] == "Hello there"

    got = get_note(USER, "MyNote")
    assert got is not None
    assert got["content"] == "Hello there"
    assert got["tags"] == ["important"]


def test_restore_note_conflict_raises(user_brain):
    create_note(USER, "MyNote", "Original")
    delete_note(USER, "MyNote", "personal", deleted_by=USER)

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    entry = next(e for e in entries if e["original_id"] == "MyNote")

    create_note(USER, "MyNote", "A new note written before the restore")

    with pytest.raises(ValueError):
        trash_handlers.restore(USER, "personal", entry)


def test_restore_folder_brings_back_contents_and_nested_tags(user_brain):
    create_folder(USER, "Projects")
    create_note(USER, "Projects/Plan", "The plan")
    set_note_tags(USER, "personal", "Projects/Plan", ["urgent"])

    delete_folder(USER, "Projects", "personal", deleted_by=USER)
    assert get_note(USER, "Projects/Plan") is None

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    entry = next(e for e in entries if e["original_id"] == "Projects")

    trash_handlers.restore(USER, "personal", entry)

    got = get_note(USER, "Projects/Plan")
    assert got is not None
    assert got["content"] == "The plan"
    assert got["tags"] == ["urgent"]


def test_access_check_always_true():
    assert trash_handlers.access_check({"name": USER}, "personal", {}) is True
