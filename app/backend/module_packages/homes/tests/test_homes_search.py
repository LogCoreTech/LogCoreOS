"""Tests for homes/manifest.py's own SearchProviderSpec (_search_homes) —
added 2026-09-20 as a deliberate v1 fast-follow (deferred when Homes first
shipped 2026-09-18) so a home is findable by name/address via the app-wide
search bar itself, the reverse direction of Homes' own tag-based
aggregation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.homes.backend import service as homes_service
from module_packages.homes.manifest import _search_homes

USER = "Alice"


@pytest.fixture()
def home(brain):
    return homes_service.create_home(
        USER, {"name": "123 Main St", "ownership_type": "rent", "address": "Springfield, IL"}
    )


def test_matches_by_name(home):
    results = _search_homes("Main St", [], {"name": USER}, "personal")
    assert any(r["record_id"] == home["id"] for r in results)


def test_matches_by_address(home):
    results = _search_homes("Springfield", [], {"name": USER}, "personal")
    assert any(r["record_id"] == home["id"] for r in results)


def test_no_match_for_unrelated_query(home):
    results = _search_homes("nonexistent street", [], {"name": USER}, "personal")
    assert results == []


def test_never_matches_its_own_tag_or_any_tag_search(home):
    """The critical exclusion: without this, a home would list itself as one
    of its own "tagged items" in GET /{id}/items, since search() fans out
    across every active provider including this one — a home carries no
    arbitrary tags of its own, only the single frozen `tag` other records
    reference, so tags=[] on every result and a tag-only search must never
    match here."""
    results = _search_homes("", [home["tag"]], {"name": USER}, "personal")
    assert results == []


def test_pool_home_visible_when_household_installed(brain):
    from services import auth_service, mod_store_service

    mod_store_service.mark_installed("household", by="test-fixture")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    homes_service.create_home(
        "_household", {"name": "Shared Cabin", "ownership_type": "own"}, workspace="personal"
    )

    results = _search_homes("Shared Cabin", [], bob, "personal")

    assert any(r["title"] == "Shared Cabin" for r in results)


def test_pool_home_excluded_when_household_not_installed(brain):
    homes_service.create_home(
        "_household", {"name": "Shared Cabin", "ownership_type": "own"}, workspace="personal"
    )

    results = _search_homes("Shared Cabin", [], {"name": "Bob"}, "personal")

    assert results == []
