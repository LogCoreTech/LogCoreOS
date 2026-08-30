"""Tests for the 6 contact/deal/interaction tools that moved into
module_packages/contacts/backend/agent_tools.py when contacts/ converted
(2026-08-28) — resolved via agent_service._execute_tool's module-dispatch
fallback (still core; routes here via this package's own execute()). No
pre-existing test coverage of these tools' actual execution logic existed
before this conversion (only their schemas, unfiltered by disabled_modules,
which is the enforcement gap this conversion closed — see
tests/test_contacts_module_conversion.py for the gating tests themselves),
so this file is new, not moved."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from services import agent_service, auth_service, contacts_service, mod_store_service


@pytest.fixture()
def users(brain):
    mod_store_service.mark_installed("contacts", by="tester")
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_list_contacts_tool_filters_by_query(users):
    contacts_service.create_contact(
        "Alice", "personal", {"type": "person", "name": "Zeb Zephyr"}, created_by="Alice"
    )
    contacts_service.create_contact(
        "Alice", "personal", {"type": "company", "name": "Acme Co"}, created_by="Alice"
    )
    result = agent_service._execute_tool(
        "list_contacts", {"query": "zeb"}, users["alice"], workspace="personal"
    )
    names = [c["name"] for c in result]
    assert names == ["Zeb Zephyr"]


def test_get_contact_tool_returns_detail_and_related_records(users):
    created = contacts_service.create_contact(
        "Alice", "personal", {"type": "person", "name": "Carol"}, created_by="Alice"
    )
    contacts_service.add_interaction(
        "Alice",
        "personal",
        created["id"],
        {"type": "call", "summary": "checked in"},
        created_by="Alice",
    )
    result = agent_service._execute_tool(
        "get_contact", {"contact_id": created["id"]}, users["alice"], workspace="personal"
    )
    assert result["contact"]["name"] == "Carol"
    assert len(result["interactions"]) == 1


def test_get_contact_tool_returns_error_for_missing_id(users):
    result = agent_service._execute_tool(
        "get_contact", {"contact_id": "does-not-exist"}, users["alice"], workspace="personal"
    )
    assert "error" in result


def test_create_contact_tool_dedups_on_existing_name_or_email(users):
    contacts_service.create_contact(
        "Alice",
        "personal",
        {"type": "person", "name": "Dana", "emails": ["dana@x.com"]},
        created_by="Alice",
    )
    result = agent_service._execute_tool(
        "create_contact",
        {"name": "Dana", "emails": ["dana@x.com"]},
        users["alice"],
        workspace="personal",
    )
    assert result["existing"] is True


def test_create_contact_tool_creates_when_no_match(users):
    result = agent_service._execute_tool(
        "create_contact", {"name": "Erin"}, users["alice"], workspace="personal"
    )
    assert result["created"] is True
    found = contacts_service.find_contact(
        "Alice", "member", False, "personal", result["contact_id"]
    )
    assert found[1]["name"] == "Erin"


def test_update_contact_tool_requires_edit_access(users):
    created = contacts_service.create_contact(
        "Alice", "personal", {"type": "person", "name": "Frank"}, created_by="Alice"
    )
    contacts_service.update_access(
        "Alice",
        "personal",
        created["id"],
        shared_with=[{"target": "Bob", "access": "contribute"}],
    )
    contacts_service.respond_share("Bob", "Alice", "personal", created["id"], True)
    result = agent_service._execute_tool(
        "update_contact",
        {"contact_id": created["id"], "fields": {"name": "Frank Renamed"}},
        users["bob"],
        workspace="personal",
    )
    assert "error" in result


def test_update_contact_tool_applies_fields_with_edit_access(users):
    created = contacts_service.create_contact(
        "Alice", "personal", {"type": "person", "name": "Gina"}, created_by="Alice"
    )
    result = agent_service._execute_tool(
        "update_contact",
        {"contact_id": created["id"], "fields": {"notes": "VIP client"}},
        users["alice"],
        workspace="personal",
    )
    assert result["updated"] is True


def test_log_interaction_tool_requires_at_least_contribute_access(users):
    created = contacts_service.create_contact(
        "Alice", "personal", {"type": "person", "name": "Hank"}, created_by="Alice"
    )
    result = agent_service._execute_tool(
        "log_interaction",
        {"contact_id": created["id"], "summary": "cold call"},
        users["bob"],
        workspace="personal",
    )
    assert "error" in result


def test_log_interaction_tool_logs_for_owner(users):
    created = contacts_service.create_contact(
        "Alice", "personal", {"type": "person", "name": "Ivy"}, created_by="Alice"
    )
    result = agent_service._execute_tool(
        "log_interaction",
        {"contact_id": created["id"], "summary": "left a voicemail"},
        users["alice"],
        workspace="personal",
    )
    assert result["logged"] is True


def test_create_deal_tool_creates_deal_for_owner(users):
    created = contacts_service.create_contact(
        "Alice", "personal", {"type": "company", "name": "Jupiter LLC"}, created_by="Alice"
    )
    result = agent_service._execute_tool(
        "create_deal",
        {"contact_id": created["id"], "title": "New roof"},
        users["alice"],
        workspace="personal",
    )
    assert result["created"] is True
    deals = contacts_service.list_deals("Alice", "personal", created["id"])
    assert deals[0]["title"] == "New roof"
