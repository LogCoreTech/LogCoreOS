"""Tests for the 6 note CRUD/folder tools that moved into
module_packages/notes/backend/agent_tools.py when notes/ converted
(2026-08-26) — sharing-aware resolution via agent_service._execute_tool's
module-dispatch fallback (still core; routes here via this package's own
execute()). Moved from tests/test_agent_notes_tools.py, which kept only its
2 search_brain tests (search_brain stays core — it isn't a notes tool, it
also rglobs journal/memory/profile files)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from services import agent_service, auth_service, mod_store_service, notes_service


@pytest.fixture()
def users(brain):
    mod_store_service.mark_installed("notes", by="tester")
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def _share(owner, path, target, access):
    notes_service.update_access(
        owner, "personal", path, shared_with=[{"target": target, "access": access}]
    )
    notes_service.respond_share(target, owner, "personal", path, accept=True)


def test_list_notes_tool_includes_shared_and_pool_notes(users):
    notes_service.create_note("Alice", "Recipe", "eggs", "personal")
    _share("Alice", "Recipe", "Bob", "read")
    notes_service.create_note("_household", "Chores", "trash", "personal")

    result = agent_service._execute_tool("list_notes", {}, users["bob"], workspace="personal")
    paths = {(r["path"], r.get("_owner")) for r in result}
    assert ("Recipe", "Alice") in paths
    assert ("Chores", "household") in paths


def test_read_note_tool_respects_read_only_share(users):
    notes_service.create_note("Alice", "Recipe", "two eggs", "personal")
    _share("Alice", "Recipe", "Bob", "read")

    result = agent_service._execute_tool(
        "read_note", {"path": "Recipe", "owner": "Alice"}, users["bob"], workspace="personal"
    )
    assert result["content"] == "two eggs"


def test_read_note_tool_denied_without_a_share(users):
    notes_service.create_note("Alice", "Private", "secret", "personal")

    result = agent_service._execute_tool(
        "read_note", {"path": "Private"}, users["bob"], workspace="personal"
    )
    assert "error" in result


def test_update_note_tool_requires_contribute_not_just_read(users):
    notes_service.create_note("Alice", "Recipe", "one egg", "personal")
    _share("Alice", "Recipe", "Bob", "read")

    denied = agent_service._execute_tool(
        "update_note",
        {"path": "Recipe", "content": "two eggs", "owner": "Alice"},
        users["bob"],
        workspace="personal",
    )
    assert "error" in denied
    assert notes_service.get_note("Alice", "Recipe", "personal")["content"] == "one egg"

    _share("Alice", "Recipe", "Bob", "contribute")
    allowed = agent_service._execute_tool(
        "update_note",
        {"path": "Recipe", "content": "two eggs", "owner": "Alice"},
        users["bob"],
        workspace="personal",
    )
    assert allowed["content"] == "two eggs"
    assert notes_service.get_note("Alice", "Recipe", "personal")["content"] == "two eggs"


def test_delete_note_tool_requires_edit_not_contribute(users):
    notes_service.create_note("Alice", "Recipe", "eggs", "personal")
    _share("Alice", "Recipe", "Bob", "contribute")

    denied = agent_service._execute_tool(
        "delete_note", {"path": "Recipe", "owner": "Alice"}, users["bob"], workspace="personal"
    )
    assert "error" in denied
    assert notes_service.get_note("Alice", "Recipe", "personal") is not None

    _share("Alice", "Recipe", "Bob", "edit")
    allowed = agent_service._execute_tool(
        "delete_note", {"path": "Recipe", "owner": "Alice"}, users["bob"], workspace="personal"
    )
    assert allowed["deleted"] is True


def test_own_note_crud_unaffected_by_the_sharing_aware_resolution(users):
    created = agent_service._execute_tool(
        "create_note", {"path": "Mine", "content": "hi"}, users["alice"], workspace="personal"
    )
    assert created["path"] == "Mine"

    updated = agent_service._execute_tool(
        "update_note", {"path": "Mine", "content": "bye"}, users["alice"], workspace="personal"
    )
    assert updated["content"] == "bye"

    moved = agent_service._execute_tool(
        "move_note", {"from_path": "Mine", "to_path": "Moved"}, users["alice"], workspace="personal"
    )
    assert moved["to_path"] == "Moved"

    deleted = agent_service._execute_tool(
        "delete_note", {"path": "Moved"}, users["alice"], workspace="personal"
    )
    assert deleted["deleted"] is True
