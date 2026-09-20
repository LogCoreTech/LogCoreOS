"""Service-level tests for module_packages/homes/backend/service.py — CRUD,
the tag generation/freeze/registration scheme, rent/own variant validation,
and trash integration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.homes.backend import service as homes_service
from services import tags_service

USER = "Alice"


def test_create_home_rent(brain):
    home = homes_service.create_home(
        USER,
        {
            "name": "123 Main St",
            "ownership_type": "rent",
            "address": "123 Main St, Springfield",
            "rent": {"monthly_rent": 1500, "lease_start": "2026-01-01", "lease_end": "2026-12-31"},
        },
    )
    assert home["ownership_type"] == "rent"
    assert home["own"] is None
    assert home["rent"]["monthly_rent"] == 1500.0
    assert home["tag"].startswith("home:123-main-st-")
    assert len(home["tag"]) <= 30


def test_create_home_own(brain):
    home = homes_service.create_home(
        USER,
        {
            "name": "The Lake House",
            "ownership_type": "own",
            "own": {"purchase_price": 350000, "purchase_date": "2020-06-15"},
        },
    )
    assert home["ownership_type"] == "own"
    assert home["rent"] is None
    assert home["own"]["purchase_price"] == 350000.0


def test_create_home_requires_name(brain):
    with pytest.raises(ValueError):
        homes_service.create_home(USER, {"name": "", "ownership_type": "rent"})


def test_create_home_requires_valid_ownership_type(brain):
    with pytest.raises(ValueError):
        homes_service.create_home(USER, {"name": "X", "ownership_type": "lease-to-own"})


def test_tag_is_registered_in_vocabulary_immediately(brain):
    home = homes_service.create_home(USER, {"name": "Cabin", "ownership_type": "own"})
    assert home["tag"] in tags_service.get_tags(USER, "personal")


def test_tag_is_frozen_on_rename(brain):
    home = homes_service.create_home(USER, {"name": "Old Name", "ownership_type": "rent"})
    original_tag = home["tag"]

    updated = homes_service.update_home(USER, home["id"], {"name": "New Name"})

    assert updated["name"] == "New Name"
    assert updated["tag"] == original_tag


def test_client_cannot_set_tag_via_update(brain):
    """update_home()'s `updates` dict is applied field-by-field for known
    keys only — a stray 'tag' key is never one of them, so it's silently
    inert even if a caller somehow constructs one (defense in depth on top
    of HomeUpdate not declaring the field at all)."""
    home = homes_service.create_home(USER, {"name": "Spoofable?", "ownership_type": "rent"})
    updated = homes_service.update_home(USER, home["id"], {"tag": "home:hijacked-0000"})
    assert updated["tag"] == home["tag"]


def test_negative_money_field_rejected(brain):
    with pytest.raises(ValueError):
        homes_service.create_home(
            USER, {"name": "X", "ownership_type": "rent", "rent": {"monthly_rent": -100}}
        )


def test_absurd_money_field_rejected(brain):
    with pytest.raises(ValueError):
        homes_service.create_home(
            USER, {"name": "X", "ownership_type": "own", "own": {"purchase_price": 10**12}}
        )


def test_comma_formatted_money_field_accepted(brain):
    """Real bug found live 2026-09-18: a human types money as '$1,617', not
    a bare float string — the frontend's own <input type="number"> used to
    silently block the whole form's submission the instant a comma was
    typed (native HTML5 validation, before onSubmit ever fires, zero
    visible error). Backend should never have been strict about this
    either, since the AI agent tools take this same field from natural
    language input."""
    home = homes_service.create_home(
        USER, {"name": "X", "ownership_type": "own", "own": {"monthly_payment": "$1,617.50"}}
    )
    assert home["own"]["monthly_payment"] == 1617.50


def test_invalid_date_field_rejected(brain):
    with pytest.raises(ValueError):
        homes_service.create_home(
            USER, {"name": "X", "ownership_type": "rent", "rent": {"lease_start": "not-a-date"}}
        )


def test_invalid_contact_id_rejected(brain):
    with pytest.raises(ValueError):
        homes_service.create_home(
            USER,
            {"name": "X", "ownership_type": "rent", "rent": {"landlord_contact_id": "nonexistent"}},
        )


def test_valid_contact_id_accepted(brain):
    from services import contacts_service

    contact = contacts_service.create_contact(
        USER, "personal", {"name": "Landlord Bob", "type": "person"}, created_by=USER
    )
    home = homes_service.create_home(
        USER,
        {
            "name": "X",
            "ownership_type": "rent",
            "rent": {"landlord_contact_id": contact["id"]},
        },
    )
    assert home["rent"]["landlord_contact_id"] == contact["id"]


def test_unknown_variant_fields_are_dropped(brain):
    home = homes_service.create_home(
        USER,
        {
            "name": "X",
            "ownership_type": "rent",
            "rent": {"monthly_rent": 100, "not_a_real_field": "x"},
        },
    )
    assert "not_a_real_field" not in home["rent"]


def test_switching_ownership_type_clears_stale_variant(brain):
    home = homes_service.create_home(
        USER, {"name": "X", "ownership_type": "rent", "rent": {"monthly_rent": 100}}
    )
    updated = homes_service.update_home(
        USER, home["id"], {"ownership_type": "own", "own": {"purchase_price": 200000}}
    )
    assert updated["rent"] is None
    assert updated["own"]["purchase_price"] == 200000.0


def test_delete_home_routes_through_trash_and_restores(brain):
    from services import mod_store_service, trash_service

    # trash_dispatch() only considers ACTIVE (installed) modules — without
    # this, the entry still gets written by soft_delete() but is filtered
    # out of list_trash_for_user() as undispatchable.
    mod_store_service.mark_installed("homes", by="test-fixture")

    home = homes_service.create_home(USER, {"name": "Doomed", "ownership_type": "rent"})
    assert homes_service.delete_home(USER, home["id"], deleted_by=USER) is True
    assert homes_service.get_home(USER, home["id"]) is None

    entries = trash_service.list_trash_for_user({"name": USER, "role": "member"}, "personal")
    entry = next(e for e in entries if e["payload"]["id"] == home["id"])
    restored = trash_service.restore(
        store_user=USER, workspace="personal", entry_id=entry["id"], actor=USER
    )
    assert restored is not None
    assert homes_service.get_home(USER, home["id"])["name"] == "Doomed"


def test_delete_missing_home_returns_false(brain):
    assert homes_service.delete_home(USER, "no-such-id") is False


def test_convert_to_pool_moves_record_and_registers_tag_in_pool_vocabulary(brain):
    home = homes_service.create_home(USER, {"name": "Cabin", "ownership_type": "own"})

    converted = homes_service.convert_to_pool(USER, home["id"], "personal", "_household")

    assert converted["id"] == home["id"]
    assert converted["tag"] == home["tag"]
    assert homes_service.get_home(USER, home["id"]) is None
    assert homes_service.get_home("_household", home["id"]) is not None
    assert converted["tag"] in tags_service.get_tags("_household", "personal")


def test_convert_missing_home_to_pool_returns_none(brain):
    assert homes_service.convert_to_pool(USER, "no-such-id", "personal", "_household") is None


def test_find_home_own_store_hit(brain):
    home = homes_service.create_home(USER, {"name": "Cabin", "ownership_type": "own"})

    found = homes_service.find_home(USER, "personal", home["id"])

    assert found == (USER, "personal", home)


def test_find_home_household_pool_hit(brain):
    home = homes_service.create_home("_household", {"name": "Shared", "ownership_type": "rent"})

    found = homes_service.find_home(USER, "personal", home["id"])

    assert found == ("_household", "personal", home)


def test_find_home_team_pool_hit(brain):
    home = homes_service.create_home("_team", {"name": "Office", "ownership_type": "rent"})

    found = homes_service.find_home(USER, "business", home["id"])

    assert found == ("_team", "personal", home)


def test_find_home_returns_none_when_not_found_anywhere(brain):
    assert homes_service.find_home(USER, "personal", "no-such-id") is None
