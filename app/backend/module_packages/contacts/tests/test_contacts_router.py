"""Router-level tests for module_packages/contacts/backend/router.py — the
first-ever HTTP-layer coverage of this router (contacts_service.py's own
CRUD/sharing/self-contact/affiliation logic is already covered extensively
by tests/test_contacts.py; this file is about the router's own body logic:
pool-default-True on create, contribute-vs-edit access enforcement,
convert-to-pool being self-service rather than admin-only, pool-delete
being admin-only, and the two admin-gated-but-not-module-gated endpoints
this conversion's own research surfaced).

Endpoint functions are called directly with a pre-resolved user dict and a
plain workspace string, matching this test suite's established convention
(see test_notes_router.py/test_assets_router.py) — Depends(_require_contacts)/
Depends(get_workspace) are bypassed the same way Depends(require_admin) is
elsewhere; this file tests the endpoints' own body logic, not the
require_module dependency chain itself (untested anywhere in this suite
today, a pre-existing, systemic gap this conversion isn't scoped to
close)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.contacts.backend.router import (
    AccessRequest,
    ContactCreate,
    ContactUpdate,
    InteractionCreate,
    ShareEntry,
    archive_contact,
    convert_contact_to_pool,
    create_contact,
    delete_contact,
    get_contact,
    list_contacts,
    list_contacts_available_for_linking,
    unarchive_contact,
    update_contact,
    update_contact_access,
)


@pytest.fixture()
def users(brain):
    from services import auth_service

    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_create_defaults_into_the_workspace_pool(users):
    created = create_contact(ContactCreate(name="Household Vendor"), users["alice"], "personal")

    assert created["_owner"] == "household"
    result = list_contacts(False, users["bob"], "personal")
    assert any(c["name"] == "Household Vendor" for c in result)


def test_create_personal_when_pool_false(users):
    created = create_contact(
        ContactCreate(name="Just Mine", pool=False), users["alice"], "personal"
    )

    assert "_owner" not in created
    result = list_contacts(False, users["bob"], "personal")
    assert not any(c["name"] == "Just Mine" for c in result)


def test_get_contact_404_when_missing(users):
    with pytest.raises(HTTPException) as exc:
        get_contact("11111111-1111-1111-1111-111111111111", users["alice"], "personal")
    assert exc.value.status_code == 404


def test_update_contact_renames(users):
    created = create_contact(
        ContactCreate(name="Old Name", pool=False), users["alice"], "personal"
    )

    result = update_contact(
        created["id"], ContactUpdate(name="New Name"), users["alice"], "personal"
    )

    assert result["name"] == "New Name"


def test_archive_and_unarchive_contact(users):
    created = create_contact(ContactCreate(name="Seasonal"), users["alice"], "personal")

    archive_contact(created["id"], users["alice"], "personal")
    result = list_contacts(False, users["alice"], "personal")
    assert not any(c["id"] == created["id"] for c in result)

    unarchive_contact(created["id"], users["alice"], "personal")
    result = list_contacts(False, users["alice"], "personal")
    assert any(c["id"] == created["id"] for c in result)


def test_delete_personal_contact(users):
    created = create_contact(
        ContactCreate(name="Disposable", pool=False), users["alice"], "personal"
    )

    delete_contact(created["id"], users["alice"], "personal")

    result = list_contacts(False, users["alice"], "personal")
    assert not any(c["id"] == created["id"] for c in result)


def test_delete_pool_contact_blocked_for_non_admin(users):
    created = create_contact(ContactCreate(name="Pool Vendor"), users["alice"], "personal")

    with pytest.raises(HTTPException) as exc:
        delete_contact(created["id"], users["bob"], "personal")
    assert exc.value.status_code == 403


def test_convert_to_pool_is_self_service_not_admin_only(users):
    """Deliberately NOT admin-gated, unlike Assets' own convert-to-pool —
    see the router's own convert_contact_to_pool docstring for why."""
    created = create_contact(
        ContactCreate(name="Bob's Contact", pool=False), users["bob"], "personal"
    )

    result = convert_contact_to_pool(created["id"], users["bob"], "personal")

    assert result["_owner"] == "household"


def test_convert_already_pool_contact_400(users):
    created = create_contact(ContactCreate(name="Already Pool"), users["alice"], "personal")

    with pytest.raises(HTTPException) as exc:
        convert_contact_to_pool(created["id"], users["alice"], "personal")
    assert exc.value.status_code == 400


def test_contribute_access_can_log_interactions_not_edit_core_fields(users):
    created = create_contact(
        ContactCreate(name="Shared Lead", pool=False), users["alice"], "personal"
    )
    update_contact_access(
        created["id"],
        AccessRequest(shared_with=[ShareEntry(target="Bob", access="contribute")]),
        users["alice"],
        "personal",
    )
    # A named-user share is a handshake, pending until accepted — same shape
    # as Notes'/Assets' own sharing models.
    from services import contacts_service

    contacts_service.respond_share("Bob", "Alice", "personal", created["id"], True)

    # Allowed: contribute can log an interaction.
    from module_packages.contacts.backend.router import add_interaction

    logged = add_interaction(
        created["id"], InteractionCreate(summary="left a voicemail"), users["bob"], "personal"
    )
    assert logged["summary"] == "left a voicemail"

    # Blocked: contribute can't rename the contact.
    with pytest.raises(HTTPException) as exc:
        update_contact(created["id"], ContactUpdate(name="Renamed"), users["bob"], "personal")
    assert exc.value.status_code == 403


def test_available_for_linking_lists_unclaimed_pool_contacts(users):
    created = create_contact(ContactCreate(name="Unclaimed Person"), users["alice"], "personal")

    result = list_contacts_available_for_linking(users["alice"], None)

    assert any(c["id"] == created["id"] for c in result)
