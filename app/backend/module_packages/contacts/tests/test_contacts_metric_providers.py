"""Tests for module_packages/contacts/manifest.py's Goals metric providers —
_resolve_number_field (admin-defined custom fields) and _resolve_weight
(the built-in, always-private weight_kg field, added 2026-08-29 after the
owner found custom-fields-only coverage missed their own weight goal)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.contacts.manifest import _resolve_number_field, _resolve_weight
from services import contacts_service


@pytest.fixture()
def alice(brain):
    from services import auth_service, mod_store_service

    mod_store_service.mark_installed("contacts", by="test")
    mod_store_service.mark_installed("household", by="test")
    user = auth_service.create_user("alice@example.com", "password123", "Alice")
    contacts_service.create_self_contact("Alice")
    yield user
    auth_service._revoked_jtis.clear()


def test_resolve_weight_reads_own_self_contact(alice):
    self_contact = contacts_service.get_self_contact("Alice")
    contacts_service.update_contact(
        "_household", "personal", self_contact["id"], {"weight_kg": 82}, viewer="Alice"
    )
    result = _resolve_weight(
        {"target_value": 75, "direction": "decrease", "start_value": 90},
        {"name": "Alice"},
        "personal",
    )
    # started 90, target 75, now 82: (90-82)/(90-75) = 53.3% -> 53
    assert result["current"] == 82
    assert result["pct"] == 53


def test_resolve_weight_no_weight_set_yet_degrades_to_zero(alice):
    result = _resolve_weight({"target_value": 75}, {"name": "Alice"}, "personal")
    assert result == {"current": 0, "target": 75, "pct": 0}


def test_resolve_weight_defaults_to_decrease_direction(alice):
    self_contact = contacts_service.get_self_contact("Alice")
    contacts_service.update_contact(
        "_household", "personal", self_contact["id"], {"weight_kg": 100}, viewer="Alice"
    )
    # No explicit direction/start_value — decrease is the default, and with
    # no start_value the first resolve reads as 0% until it actually moves.
    result = _resolve_weight({"target_value": 80}, {"name": "Alice"}, "personal")
    assert result["pct"] == 0


def test_resolve_number_field_still_reads_custom_fields(alice):
    contacts_service.set_custom_fields(
        [{"key": "resting_hr", "label": "Resting HR", "type": "number"}]
    )
    self_contact = contacts_service.get_self_contact("Alice")
    contacts_service.update_contact(
        "_household", "personal", self_contact["id"], {"custom": {"resting_hr": 60}}, viewer="Alice"
    )
    result = _resolve_number_field(
        {"field_key": "resting_hr", "target_value": 50, "direction": "decrease", "start_value": 70},
        {"name": "Alice"},
        "personal",
    )
    # started 70, target 50, now 60: (70-60)/(70-50) = 50%
    assert result["pct"] == 50
