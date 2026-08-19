"""Tests for services/profile_service.py — narrowed to pool priority order
after the Profile/Contacts merge. Real-user profile behavior now lives on the
self-contact and is covered in test_contacts_service.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import services.profile_service as svc
from services.file_service import write_json, ws_path

USER = "TestUser"


@pytest.fixture()
def user_dir(brain):
    d = brain / "USERS" / USER
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# get_priority_order — pool pseudo-users (still read profile.json directly)
# ---------------------------------------------------------------------------


def test_get_priority_order_pool_from_json(brain):
    (brain / "USERS" / "_household").mkdir(parents=True, exist_ok=True)
    write_json(ws_path("_household", "personal") / "profile.json", {"priority_order": ["A", "B"]})
    assert svc.get_priority_order("_household") == ["A", "B"]


def test_get_priority_order_pool_fallback_to_defaults(brain):
    (brain / "USERS" / "_team").mkdir(parents=True, exist_ok=True)
    assert svc.get_priority_order("_team") == svc.DEFAULT_PRIORITY_ORDER


# ---------------------------------------------------------------------------
# get_priority_order — real users (repointed to the self-contact)
# ---------------------------------------------------------------------------


def test_get_priority_order_real_user_creates_self_contact(user_dir):
    from services import contacts_service

    assert contacts_service.get_self_contact(USER) is None
    order = svc.get_priority_order(USER)
    assert order == svc.DEFAULT_PRIORITY_ORDER
    assert contacts_service.get_self_contact(USER) is not None


def test_get_priority_order_real_user_reads_workspace_slice(user_dir):
    from services import contacts_service

    contact = contacts_service.create_self_contact(USER)
    contacts_service.update_contact(
        contacts_service.POOL_HOUSEHOLD,
        "personal",
        contact["id"],
        {"priority_order": {"personal": ["Health", "Family"], "business": ["Revenue"]}},
    )
    assert svc.get_priority_order(USER, "personal") == ["Health", "Family"]
    assert svc.get_priority_order(USER, "business") == ["Revenue"]


def test_get_priority_order_real_user_missing_workspace_slice_defaults(user_dir):
    from services import contacts_service

    contact = contacts_service.create_self_contact(USER)
    contacts_service.update_contact(
        contacts_service.POOL_HOUSEHOLD,
        "personal",
        contact["id"],
        {"priority_order": {"personal": ["Health"]}},
    )
    assert svc.get_priority_order(USER, "business") == svc.DEFAULT_PRIORITY_ORDER
