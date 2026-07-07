"""Tests for agent member-name resolution on shared task assignment."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import auth_service, task_service
from services.agent_service import _execute_tool, _resolve_member_name


@pytest.fixture()
def members(brain):
    """Three users: an admin plus two members whose first names collide on a prefix."""
    admin = auth_service.create_user(
        "admin@example.com", "password123", "Alice Smith", role="admin"
    )
    auth_service.create_user("bob@example.com", "password123", "Bob Jones")
    auth_service.create_user("bonnie@example.com", "password123", "Bonnie Ray")
    yield admin
    auth_service._revoked_jtis.clear()


# ---------------------------------------------------------------------------
# _resolve_member_name
# ---------------------------------------------------------------------------


def test_exact_full_name(members):
    assert _resolve_member_name("Bob Jones") == ("Bob Jones", None)


def test_exact_full_name_case_insensitive(members):
    assert _resolve_member_name("bob jones") == ("Bob Jones", None)


def test_first_name_match(members):
    assert _resolve_member_name("bob") == ("Bob Jones", None)


def test_first_name_prefix_match(members):
    assert _resolve_member_name("ali") == ("Alice Smith", None)


def test_ambiguous_prefix_returns_error_with_candidates(members):
    resolved, err = _resolve_member_name("bo")
    assert resolved is None
    assert "Bob Jones" in err and "Bonnie Ray" in err
    assert "Ask the user" in err


def test_unknown_name_returns_error_listing_members(members):
    resolved, err = _resolve_member_name("charlie")
    assert resolved is None
    assert "Bob Jones" in err and "Bonnie Ray" in err and "Alice Smith" in err
    assert "do not guess" in err


def test_empty_name_returns_error(members):
    resolved, err = _resolve_member_name("   ")
    assert resolved is None
    assert "cannot be empty" in err


# ---------------------------------------------------------------------------
# Tool executor integration
# ---------------------------------------------------------------------------


def test_add_shared_task_resolves_first_name(members):
    result = _execute_tool(
        "add_shared_task",
        {"title": "Take out trash", "category": "Home", "assigned_to": "bob"},
        members,
    )
    assert result["assigned_to"] == "Bob Jones"
    stored = task_service.list_tasks("_household")
    assert stored[0]["assigned_to"] == "Bob Jones"


def test_add_shared_task_unknown_name_rejected(members):
    result = _execute_tool(
        "add_shared_task",
        {"title": "Take out trash", "category": "Home", "assigned_to": "charlie"},
        members,
    )
    assert "error" in result
    assert task_service.list_tasks("_household") == []


def test_add_shared_task_ambiguous_name_rejected(members):
    result = _execute_tool(
        "add_shared_task",
        {"title": "Take out trash", "category": "Home", "assigned_to": "bo"},
        members,
    )
    assert "error" in result
    assert task_service.list_tasks("_household") == []


def test_add_shared_task_without_assignment_still_works(members):
    result = _execute_tool("add_shared_task", {"title": "Sweep", "category": "Home"}, members)
    assert result["title"] == "Sweep"
    assert "error" not in result


def test_update_shared_task_resolves_reassignment(members):
    task = _execute_tool(
        "add_shared_task",
        {"title": "Dishes", "category": "Home", "assigned_to": "bob"},
        members,
    )
    result = _execute_tool(
        "update_shared_task",
        {"task_id": task["id"], "assigned_to": "bonnie"},
        members,
    )
    assert result["assigned_to"] == "Bonnie Ray"


def test_update_shared_task_unknown_name_rejected(members):
    task = _execute_tool(
        "add_shared_task",
        {"title": "Dishes", "category": "Home", "assigned_to": "bob"},
        members,
    )
    result = _execute_tool(
        "update_shared_task",
        {"task_id": task["id"], "assigned_to": "charlie"},
        members,
    )
    assert "error" in result
    assert task_service.get_task("_household", task["id"])["assigned_to"] == "Bob Jones"


def test_update_shared_task_null_clears_assignment(members):
    task = _execute_tool(
        "add_shared_task",
        {"title": "Dishes", "category": "Home", "assigned_to": "bob"},
        members,
    )
    result = _execute_tool(
        "update_shared_task",
        {"task_id": task["id"], "assigned_to": None},
        members,
    )
    assert result["assigned_to"] is None


def test_list_household_members(members):
    result = _execute_tool("list_household_members", {}, members)
    assert {"name": "Bob Jones"} in result and {"name": "Bonnie Ray"} in result


def test_list_household_members_requires_admin(members):
    non_admin = auth_service.get_user_by_email("bob@example.com")
    result = _execute_tool("list_household_members", {}, non_admin)
    assert result == {"error": "Admin access required"}
