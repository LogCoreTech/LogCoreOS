"""The automation upsert (POST /contacts/automation/contacts) must MERGE into an
existing contact, never wipe it. Before 2026-10-25 `req.model_dump()` sent every
omitted field as None and `_validate_contact(partial=True)` treated each as a
replacement, so a sparse second call (name + a new phone) erased emails, tags
and notes and replaced the phones. Also covers the phone/external_id dedup
added alongside the fix (the same phone under a different name used to
create a duplicate)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.contacts.backend import router_automation as ra
from services import contacts_service as crm


@pytest.fixture(autouse=True)
def known_user(brain, monkeypatch):
    monkeypatch.setattr(ra, "get_user_by_name", lambda name: {"name": name})


def _upsert(**kw):
    return ra.automation_upsert_contact(ra.AutoContact(user="Owner", **kw), None, None)


def _only_contact():
    contacts = crm.list_contacts("Owner", "personal")
    assert len(contacts) == 1
    return contacts[0]


def test_sparse_second_upsert_keeps_existing_fields(brain):
    first = _upsert(
        name="Dana Smith",
        emails=["dana@example.com"],
        phones=["501-555-0100"],
        tags=["lead"],
        notes="Called about a quote",
    )
    assert first["created"] is True

    second = _upsert(name="Dana Smith", phones=["501-555-0199"])
    assert second == {"id": first["id"], "created": False}

    c = _only_contact()
    assert c["emails"] == ["dana@example.com"]
    assert c["tags"] == ["lead"]
    assert c["notes"] == "Called about a quote"
    assert [p["number"] for p in c["phones"]] == ["5015550100", "5015550199"]


def test_same_phone_different_format_and_name_dedups(brain):
    first = _upsert(name="Dana Smith", phones=["(501) 555-0100"])
    second = _upsert(name="D. Smith", phones=["+1 501-555-0100"])
    assert second["id"] == first["id"]
    c = _only_contact()
    assert c["name"] == "Dana Smith"  # the existing name is kept
    assert len(c["phones"]) == 1


def test_external_id_dedups_and_is_persisted(brain):
    first = _upsert(name="Dana Smith", external_id="form-123")
    assert _only_contact()["external_id"] == "form-123"
    second = _upsert(name="Someone Else", external_id="form-123")
    assert second["id"] == first["id"]


def test_tags_union_and_notes_append(brain):
    _upsert(name="Dana Smith", tags=["lead"], notes="First message")
    _upsert(name="Dana Smith", tags=["Lead", "website"], notes="Second message")
    c = _only_contact()
    assert c["tags"] == ["lead", "website"]
    assert c["notes"] == "First message\n\nSecond message"


def test_repeated_identical_note_is_not_duplicated(brain):
    _upsert(name="Dana Smith", notes="Same text")
    _upsert(name="Dana Smith", notes="Same text")
    assert _only_contact()["notes"] == "Same text"


def test_no_match_creates_new_contact(brain):
    _upsert(name="Dana Smith", phones=["501-555-0100"])
    created = _upsert(name="Lee Jones", phones=["501-555-0111"])
    assert created["created"] is True
    assert len(crm.list_contacts("Owner", "personal")) == 2


def test_lookup_by_phone_and_external_id(brain):
    first = _upsert(name="Dana Smith", phones=["501-555-0100"], external_id="x-1")
    by_phone = ra.automation_lookup(user="Owner", phone="5015550100", _auth=None, _rl=None)
    by_ext = ra.automation_lookup(user="Owner", external_id="x-1", _auth=None, _rl=None)
    assert by_phone == {"found": True, "contact_id": first["id"]}
    assert by_ext == {"found": True, "contact_id": first["id"]}


def test_find_match_prefers_stronger_signal_across_store(brain):
    by_name = crm.create_contact("Owner", "personal", {"name": "Pat"}, created_by="t")
    by_email = crm.create_contact(
        "Owner", "personal", {"name": "Patricia", "emails": ["pat@example.com"]}, created_by="t"
    )
    match = crm.find_match("Owner", "personal", name="Pat", email="pat@example.com")
    assert match["id"] == by_email["id"] != by_name["id"]


def test_short_phone_never_matches(brain):
    crm.create_contact("Owner", "personal", {"name": "A", "phones": ["911"]}, created_by="t")
    assert crm.find_match("Owner", "personal", phone="911") is None


def test_phone_with_country_code_is_not_truncated(brain):
    _upsert(name="Dana Smith", phones=["+1 501-555-0100", "+44 20 7946 0958"])
    phones = _only_contact()["phones"]
    assert phones[0] == {"country_code": "1", "number": "5015550100", "extension": ""}
    assert phones[1] == {"country_code": "44", "number": "2079460958", "extension": ""}
