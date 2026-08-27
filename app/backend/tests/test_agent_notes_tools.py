"""search_brain's note-sharing awareness — the only note-adjacent AI tool
that stays core (it also rglobs journal/memory/profile files, so it isn't
notes-owned). The other 6 note CRUD/folder tools moved to
module_packages/notes/tests/test_notes_agent_tools.py when notes/ converted
(2026-08-26).

search_brain's own-files half (a plain rglob) was already correctly gated by
_brain_skip() before this conversion — Notes just wasn't in that skip set
yet. Its SECOND half (shared/pool notes, reached directly via
notes_service.list_visible_notes rather than the rglob walk) was NOT gated
at all until a follow-up fix the same day, found while answering a real
question about whether uninstalling notes could affect other modules' data
— it doesn't, but this loop's own gap was real: a user with notes disabled
could still search content from notes shared *with* them or in the
household/team pool, even though their own Notes/ folder was correctly
hidden by the first half. Both halves now key off the same `skip` set."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import agent_service, auth_service, notes_service


@pytest.fixture()
def users(brain):
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def _share(owner, path, target, access):
    notes_service.update_access(
        owner, "personal", path, shared_with=[{"target": target, "access": access}]
    )
    notes_service.respond_share(target, owner, "personal", path, accept=True)


def test_search_brain_finds_content_inside_a_shared_note(users):
    notes_service.create_note("Alice", "Recipe", "the secret ingredient is nutmeg", "personal")
    _share("Alice", "Recipe", "Bob", "read")

    result = agent_service._execute_tool(
        "search_brain", {"query": "nutmeg"}, users["bob"], workspace="personal"
    )
    hits = [r for r in result if r["path"] == "Notes/Recipe.md"]
    assert len(hits) == 1
    assert hits[0]["owner"] == "Alice"


def test_search_brain_still_finds_own_notes(users):
    notes_service.create_note("Bob", "MyNote", "a private nutmeg reference", "personal")

    result = agent_service._execute_tool(
        "search_brain", {"query": "nutmeg"}, users["bob"], workspace="personal"
    )
    hits = [r for r in result if r["path"] == "Notes/MyNote.md"]
    assert len(hits) == 1
    assert hits[0]["owner"] is None


def test_search_brain_hides_shared_note_content_when_notes_disabled_for_viewer(users):
    """The gap found and fixed 2026-08-26: shared/pool note content reached
    via notes_service.list_visible_notes bypassed the rglob walk's own
    _brain_skip() gate entirely — a disabled viewer could still search
    content shared with them even though their own notes were hidden."""
    notes_service.create_note("Alice", "Recipe", "the secret ingredient is nutmeg", "personal")
    _share("Alice", "Recipe", "Bob", "read")

    disabled_bob = {**users["bob"], "disabled_modules": ["notes"]}
    result = agent_service._execute_tool(
        "search_brain", {"query": "nutmeg"}, disabled_bob, workspace="personal"
    )
    assert not any(r["path"] == "Notes/Recipe.md" for r in result)
