"""Tests for contacts/backend/trash_handlers.py — the per-module side of the
trash registry contract (see services/trash_service.py's module docstring
and module_registry.py's trash_dispatch()/owned_trash_types). Contacts is
the first module where a sub-record (interactions/deals) deliberately stays
hard-deleted — only snapshotted for a restore-time warning, never brought
back."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.contacts.backend import trash_handlers
from module_packages.contacts.manifest import MODULE
from services import auth_service, mod_store_service
from services.contacts_service import (
    add_deal,
    add_interaction,
    create_contact,
    delete_contact,
    get_contact,
    list_contacts,
)

USER = "TestUser"


@pytest.fixture()
def user_brain(brain):
    mod_store_service.mark_installed("contacts", by="test-fixture")
    user_dir = brain / "USERS" / USER / "Contacts"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def test_record_types_match_manifest():
    assert trash_handlers.RECORD_TYPES == MODULE.owned_trash_types


def test_describe_plain_contact_no_sub_records():
    title, subtitle = trash_handlers.describe("contact", {"name": "Jane Doe"})
    assert title == "Jane Doe"
    assert subtitle == "Contacts"


def test_describe_warns_about_unrestorable_sub_records():
    payload = {
        "name": "Jane Doe",
        "_trashed_interactions": [{"id": "i1"}],
        "_trashed_deals": [{"id": "d1"}, {"id": "d2"}],
    }
    title, subtitle = trash_handlers.describe("contact", payload)
    assert title == "Jane Doe"
    assert "1 interaction" in subtitle
    assert "2 deals" in subtitle
    assert "not restorable" in subtitle


def test_restore_reinserts_contact(user_brain):
    contact = create_contact(USER, "personal", {"name": "Jane Doe"}, created_by=USER)

    delete_contact(USER, "personal", contact["id"], deleted_by=USER)
    assert get_contact(USER, "personal", contact["id"]) is None

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    entry = next(e for e in entries if e["original_id"] == contact["id"])

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["id"] == contact["id"]
    assert get_contact(USER, "personal", contact["id"]) is not None


def test_restore_warns_when_interactions_or_deals_were_lost(user_brain):
    contact = create_contact(USER, "personal", {"name": "Jane Doe"}, created_by=USER)
    add_interaction(USER, "personal", contact["id"], {"summary": "Called"}, created_by=USER)
    add_deal(
        USER,
        "personal",
        contact["id"],
        {"title": "Big deal", "value_cents": 10000},
        created_by=USER,
    )

    delete_contact(USER, "personal", contact["id"], deleted_by=USER)

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    entry = next(e for e in entries if e["original_id"] == contact["id"])

    restored = trash_handlers.restore(USER, "personal", entry)
    assert "_warning" in restored
    assert "could not be restored" in restored["_warning"]


def test_restore_conflict_raises_when_id_already_present(user_brain):
    contact = create_contact(USER, "personal", {"name": "Jane Doe"}, created_by=USER)
    entry = {"payload": dict(contact)}

    with pytest.raises(ValueError):
        trash_handlers.restore(USER, "personal", entry)


def test_access_check_always_true():
    assert trash_handlers.access_check({"name": USER}, "personal", {}) is True
