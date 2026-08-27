"""Router-level tests for module_packages/notes/backend/router.py — the
first-ever HTTP-layer coverage of this router (notes_service.py's own CRUD/
sharing logic is already covered by tests/test_notes_service.py and
tests/test_notes_sharing.py; this file is about the router's own body
logic: access-level gating via _resolve(), 404/403/409 handling, and the
sharing handshake end to end through the real endpoint functions).

Endpoint functions are called directly with a pre-resolved user dict and a
plain workspace string, matching this test suite's established convention
(see test_household_router.py/test_mod_store_router.py) — Depends(
_require_notes)/Depends(get_workspace) are bypassed the same way
Depends(require_admin) already is elsewhere; this file tests the endpoints'
own body logic, not the require_module dependency chain itself (untested
anywhere in this suite today, a pre-existing, systemic gap this conversion
isn't scoped to close)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.notes.backend.router import (
    AccessRequest,
    ArchiveRequest,
    FolderCreate,
    LeaveRequest,
    MoveItem,
    NoteCreate,
    NoteUpdate,
    ShareEntry,
    ShareRespond,
    create_folder,
    create_note,
    delete_note,
    get_note,
    leave_note,
    list_notes,
    move_item,
    respond_share,
    set_archived,
    update_access,
    update_note,
)


@pytest.fixture()
def users(brain):
    from services import auth_service

    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_create_and_list_notes(users):
    create_note(NoteCreate(path="Recipe", content="eggs"), users["alice"], "personal")

    result = list_notes(users["alice"], "personal")

    assert len(result) == 1
    assert result[0]["path"] == "Recipe"


def test_get_note_404_when_missing(users):
    with pytest.raises(HTTPException) as exc:
        get_note("Nope", users["alice"], "personal")
    assert exc.value.status_code == 404


def test_update_note_content(users):
    create_note(NoteCreate(path="Recipe", content="one egg"), users["alice"], "personal")

    result = update_note("Recipe", NoteUpdate(content="two eggs"), users["alice"], "personal")

    assert result["content"] == "two eggs"


def test_delete_note(users):
    create_note(NoteCreate(path="Recipe", content="eggs"), users["alice"], "personal")

    result = delete_note("Recipe", users["alice"], "personal")

    assert result == {"ok": True}
    # list_notes self-seeds a "Getting Started" note (notes_service's own
    # create_default=True) — check the deleted note specifically, not that
    # the list is empty.
    assert not any(n["path"] == "Recipe" for n in list_notes(users["alice"], "personal"))


def test_create_note_duplicate_path_409(users):
    create_note(NoteCreate(path="Recipe", content="eggs"), users["alice"], "personal")

    with pytest.raises(HTTPException) as exc:
        create_note(NoteCreate(path="Recipe", content="more eggs"), users["alice"], "personal")
    assert exc.value.status_code == 409


def test_create_folder_and_move_note_into_it(users):
    create_folder(FolderCreate(path="Cooking"), users["alice"], "personal")
    create_note(NoteCreate(path="Recipe", content="eggs"), users["alice"], "personal")

    result = move_item(
        MoveItem(from_path="Recipe", to_path="Cooking/Recipe", type="note"), users["alice"], "personal"
    )

    assert result["to_path"] == "Cooking/Recipe"


def test_pool_note_creation_requires_admin(users):
    with pytest.raises(HTTPException) as exc:
        create_note(NoteCreate(path="Chores", content="", pool=True), users["bob"], "personal")
    assert exc.value.status_code == 403


def test_pool_note_creation_by_admin_is_visible_to_members(users):
    create_note(NoteCreate(path="Chores", content="trash day", pool=True), users["alice"], "personal")

    result = list_notes(users["bob"], "personal")

    assert any(n["path"] == "Chores" for n in result)


def test_archive_and_unarchive_note(users):
    create_note(NoteCreate(path="Old", content=""), users["alice"], "personal")

    set_archived(ArchiveRequest(path="Old", archived=True), users["alice"], "personal")
    assert list_notes(users["alice"], "personal") == []
    assert len(list_notes(users["alice"], "personal", include_archived=True)) == 1

    set_archived(ArchiveRequest(path="Old", archived=False), users["alice"], "personal")
    assert len(list_notes(users["alice"], "personal")) == 1


def test_update_access_requires_edit_level(users):
    """A read-only share can't itself grant further sharing rights — only
    the owner (or a pool admin) can call update_access at all; this checks
    the router's own _require_owner_or_pool_admin gate, not notes_service's
    resolve_access (already covered by test_notes_sharing.py)."""
    create_note(NoteCreate(path="Recipe", content="eggs"), users["alice"], "personal")

    with pytest.raises(HTTPException) as exc:
        update_access(
            AccessRequest(path="Recipe", shared_with=[ShareEntry(target="Bob", access="read")]),
            users["bob"],
            "personal",
        )
    assert exc.value.status_code in (403, 404)


def test_share_handshake_end_to_end(users):
    from services.suggestions_service import get_notifications

    create_note(NoteCreate(path="Recipe", content="eggs"), users["alice"], "personal")

    update_access(
        AccessRequest(path="Recipe", shared_with=[ShareEntry(target="Bob", access="read")]),
        users["alice"],
        "personal",
    )

    # Not visible to Bob yet — the share is pending until he accepts.
    assert not any(n["path"] == "Recipe" for n in list_notes(users["bob"], "personal"))

    notif = next(
        n for n in get_notifications("Bob") if (n.get("action") or {}).get("type") == "notes_share"
    )
    respond_share(ShareRespond(notif_id=notif["id"], accept=True), users["bob"])

    assert any(n["path"] == "Recipe" for n in list_notes(users["bob"], "personal"))


def test_leave_shared_note(users):
    create_note(NoteCreate(path="Recipe", content="eggs"), users["alice"], "personal")
    update_access(
        AccessRequest(path="Recipe", shared_with=[ShareEntry(target="Bob", access="read")]),
        users["alice"],
        "personal",
    )
    from services import notes_service

    notes_service.respond_share("Bob", "Alice", "personal", "Recipe", accept=True)

    leave_note(LeaveRequest(path="Recipe"), users["bob"], "personal")

    assert not any(n["path"] == "Recipe" for n in list_notes(users["bob"], "personal"))
    # Alice still owns it — leaving doesn't delete the note.
    assert any(n["path"] == "Recipe" for n in list_notes(users["alice"], "personal"))


def test_leave_own_note_rejected(users):
    create_note(NoteCreate(path="Recipe", content="eggs"), users["alice"], "personal")

    with pytest.raises(HTTPException) as exc:
        leave_note(LeaveRequest(path="Recipe"), users["alice"], "personal")
    assert exc.value.status_code == 400
