"""Tests for services/notes_service.py."""

import pytest

import services.notes_service as svc

USER = "TestUser"


@pytest.fixture()
def notes_root(brain):
    """Ensure the user directory exists and return the Notes root path."""
    root = brain / "USERS" / USER / "Notes"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# list_notes
# ---------------------------------------------------------------------------


def test_list_notes_empty(brain):
    assert svc.list_notes(USER) == []


def test_list_notes_returns_note(notes_root):
    (notes_root / "hello.md").write_text("# Hello")
    items = svc.list_notes(USER)
    assert len(items) == 1
    assert items[0]["type"] == "note"
    assert items[0]["path"] == "hello"


def test_list_notes_returns_folder(notes_root):
    (notes_root / "Work").mkdir()
    items = svc.list_notes(USER)
    assert any(i["type"] == "folder" and i["path"] == "Work" for i in items)


# ---------------------------------------------------------------------------
# create_note
# ---------------------------------------------------------------------------


def test_create_note_success(notes_root):
    result = svc.create_note(USER, "my-note", "content here")
    assert result["path"] == "my-note"
    assert result["content"] == "content here"
    assert (notes_root / "my-note.md").exists()


def test_create_note_duplicate_raises(notes_root):
    svc.create_note(USER, "dup", "first")
    with pytest.raises(ValueError, match="already exists"):
        svc.create_note(USER, "dup", "second")


def test_create_note_nested_folder(notes_root):
    result = svc.create_note(USER, "Work/project-ideas", "ideas")
    assert result["path"] == "Work/project-ideas"
    assert (notes_root / "Work" / "project-ideas.md").exists()


# ---------------------------------------------------------------------------
# get_note
# ---------------------------------------------------------------------------


def test_get_note_success(notes_root):
    (notes_root / "existing.md").write_text("hello")
    result = svc.get_note(USER, "existing")
    assert result is not None
    assert result["content"] == "hello"


def test_get_note_not_found(notes_root):
    assert svc.get_note(USER, "missing") is None


# ---------------------------------------------------------------------------
# update_note
# ---------------------------------------------------------------------------


def test_update_note_success(notes_root):
    svc.create_note(USER, "editable", "v1")
    result = svc.update_note(USER, "editable", "v2")
    assert result is not None
    assert result["content"] == "v2"


def test_update_note_not_found(notes_root):
    assert svc.update_note(USER, "ghost", "content") is None


# ---------------------------------------------------------------------------
# delete_note
# ---------------------------------------------------------------------------


def test_delete_note_success(notes_root):
    svc.create_note(USER, "temp", "data")
    assert svc.delete_note(USER, "temp") is True
    assert not (notes_root / "temp.md").exists()


def test_delete_note_not_found(notes_root):
    assert svc.delete_note(USER, "nonexistent") is False


# ---------------------------------------------------------------------------
# create_folder / delete_folder
# ---------------------------------------------------------------------------


def test_create_folder_success(notes_root):
    result = svc.create_folder(USER, "Archive")
    assert result["type"] == "folder"
    assert (notes_root / "Archive").is_dir()


def test_create_folder_duplicate_raises(notes_root):
    svc.create_folder(USER, "Archive")
    with pytest.raises(ValueError, match="already exists"):
        svc.create_folder(USER, "Archive")


def test_delete_folder_success(notes_root):
    svc.create_folder(USER, "ToDelete")
    assert svc.delete_folder(USER, "ToDelete") is True
    assert not (notes_root / "ToDelete").exists()


def test_delete_folder_not_found(notes_root):
    assert svc.delete_folder(USER, "ghost") is False


# ---------------------------------------------------------------------------
# move_item
# ---------------------------------------------------------------------------


def test_move_note(notes_root):
    svc.create_note(USER, "original", "text")
    result = svc.move_item(USER, "original", "renamed", "note")
    assert result["to_path"] == "renamed"
    assert (notes_root / "renamed.md").exists()
    assert not (notes_root / "original.md").exists()


def test_move_folder(notes_root):
    svc.create_folder(USER, "OldName")
    result = svc.move_item(USER, "OldName", "NewName", "folder")
    assert result["to_path"] == "NewName"
    assert (notes_root / "NewName").is_dir()


def test_move_missing_source_raises(notes_root):
    with pytest.raises(ValueError, match="Source not found"):
        svc.move_item(USER, "nope", "dest", "note")


def test_move_existing_destination_raises(notes_root):
    svc.create_note(USER, "src", "a")
    svc.create_note(USER, "dst", "b")
    with pytest.raises(ValueError, match="Destination already exists"):
        svc.move_item(USER, "src", "dst", "note")


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape",
        "a/../b",
        "",
        ".",
        "valid/./invalid",
        "has;semicolon",
    ],
)
def test_invalid_paths_rejected(notes_root, bad_path):
    with pytest.raises(ValueError):
        svc.get_note(USER, bad_path)
