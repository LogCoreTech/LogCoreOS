"""Tests for the Contacts List block — moved from tests/test_dashboards_service.py
when contacts/ converted (2026-08-28), since resolve_contacts_list() moved
into module_packages/contacts/backend/dashboard_block.py (from the old,
shared dashboard_blocks/_contacts.py), gaining module="contacts" gating
for the first time. linked_deals/linked_assets moved into the same file
but had no existing test coverage to move — see
module_packages/contacts/tests/test_contacts_router.py for router-level
coverage of the underlying data those two resolvers read."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from services import auth_service, contacts_service
from services.dashboard_blocks.registry import BlockRenderCtx, _load_all_resolvers

_load_all_resolvers()

from module_packages.contacts.backend.dashboard_block import resolve_contacts_list


@pytest.fixture()
def users(brain):
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def _ctx(viewer="Alice", config=None, workspace="personal", is_admin=False, owner="Alice"):
    return BlockRenderCtx(
        viewer=viewer,
        viewer_role="member",
        is_admin=is_admin,
        workspace=workspace,
        config=config or {},
        dashboard_owner=owner,
    )


def test_contacts_list_returns_visible_contacts_alphabetically(users):
    contacts_service.create_contact(
        "Alice", "personal", {"type": "person", "name": "Zeb"}, created_by="Alice"
    )
    contacts_service.create_contact(
        "Alice", "personal", {"type": "company", "name": "Acme Co"}, created_by="Alice"
    )
    result = resolve_contacts_list(_ctx())
    assert result.ok is True
    names = [c["name"] for c in result.data["contacts"]]
    assert names == sorted(names, key=str.lower)
    assert "Acme Co" in names and "Zeb" in names


def test_contacts_list_scoped_to_viewer_visibility(users):
    contacts_service.create_contact(
        "Alice", "personal", {"type": "person", "name": "Alice-only"}, created_by="Alice"
    )
    result = resolve_contacts_list(_ctx(viewer="Bob"))
    assert result.ok is True
    # Bob sees his own (auto-created) self-contact, never Alice's unshared one.
    names = [c["name"] for c in result.data["contacts"]]
    assert "Alice-only" not in names


def test_contacts_list_caps_at_ten(users):
    for i in range(15):
        contacts_service.create_contact(
            "Alice", "personal", {"type": "person", "name": f"Contact {i:02d}"}, created_by="Alice"
        )
    result = resolve_contacts_list(_ctx())
    assert len(result.data["contacts"]) == 10
