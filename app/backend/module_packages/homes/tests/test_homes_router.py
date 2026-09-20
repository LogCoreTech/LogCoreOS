"""Router-level tests for module_packages/homes/backend/router.py — personal
+ pool CRUD, the explicit `pool: bool` flag routing (not id-inference), IDOR
(a home id belonging to a different store 404s rather than leaking
existence), pool_edit write gating, bulk-delete per-item reporting, and the
cross-module tagged-items aggregation endpoint (including a real pool
end-to-end check, not just trusting the design by inference). Endpoint
functions called directly with a pre-resolved user dict + plain workspace
string, matching this suite's established convention
(test_goals_router.py/test_contacts_router.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.homes.backend.router import (
    BulkDeleteRequest,
    HomeCreate,
    HomeUpdate,
    bulk_delete_homes,
    convert_home_to_pool,
    create_home,
    delete_home,
    get_home,
    get_home_items,
    list_homes,
    update_home,
)


@pytest.fixture()
def users(brain):
    from services import auth_service, mod_store_service

    mod_store_service.mark_installed("homes", by="test-fixture")
    mod_store_service.mark_installed("household", by="test-fixture")
    admin = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": admin, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_create_and_list_personal_home(users):
    created = create_home(
        HomeCreate(name="123 Main St", ownership_type="rent"), users["bob"], "personal"
    )
    assert created["name"] == "123 Main St"

    listed = list_homes(users["bob"], "personal")
    assert any(h["id"] == created["id"] for h in listed)
    # Not visible to Alice — Bob's personal home, not pool
    assert not any(h["id"] == created["id"] for h in list_homes(users["alice"], "personal"))


def test_get_home_404_when_missing(users):
    with pytest.raises(HTTPException) as exc:
        get_home("11111111-1111-1111-1111-111111111111", False, users["bob"], "personal")
    assert exc.value.status_code == 404


def test_get_home_404_not_leaked_across_users(users):
    """The core IDOR check: a home id that's real, just not in the CALLER's
    own resolved store, 404s exactly like a nonexistent id — no way to
    distinguish "doesn't exist" from "exists but isn't yours"."""
    bobs_home = create_home(
        HomeCreate(name="Bob's place", ownership_type="rent"), users["bob"], "personal"
    )

    with pytest.raises(HTTPException) as exc:
        get_home(bobs_home["id"], False, users["alice"], "personal")
    assert exc.value.status_code == 404


def test_invalid_id_format_rejected(users):
    with pytest.raises(HTTPException) as exc:
        get_home("not-a-uuid", False, users["bob"], "personal")
    assert exc.value.status_code == 400


def test_update_home(users):
    created = create_home(HomeCreate(name="Old", ownership_type="rent"), users["bob"], "personal")
    result = update_home(created["id"], HomeUpdate(name="New"), users["bob"], "personal")
    assert result["name"] == "New"


def test_update_home_404_across_users(users):
    bobs_home = create_home(
        HomeCreate(name="Bob's place", ownership_type="rent"), users["bob"], "personal"
    )
    with pytest.raises(HTTPException) as exc:
        update_home(bobs_home["id"], HomeUpdate(name="Hijacked"), users["alice"], "personal")
    assert exc.value.status_code == 404


def test_delete_home(users):
    created = create_home(
        HomeCreate(name="Doomed", ownership_type="rent"), users["bob"], "personal"
    )
    delete_home(created["id"], False, users["bob"], "personal")
    with pytest.raises(HTTPException):
        get_home(created["id"], False, users["bob"], "personal")


def test_delete_home_404_across_users(users):
    bobs_home = create_home(
        HomeCreate(name="Bob's place", ownership_type="rent"), users["bob"], "personal"
    )
    with pytest.raises(HTTPException) as exc:
        delete_home(bobs_home["id"], False, users["alice"], "personal")
    assert exc.value.status_code == 404
    # Confirm it wasn't actually deleted by the failed attempt.
    assert get_home(bobs_home["id"], False, users["bob"], "personal") is not None


def test_member_cannot_create_pool_home_without_grant(users):
    with pytest.raises(HTTPException) as exc:
        create_home(
            HomeCreate(name="Shared house", ownership_type="own", pool=True),
            users["bob"],
            "personal",
        )
    assert exc.value.status_code == 403


def test_admin_can_create_pool_home(users):
    created = create_home(
        HomeCreate(name="Shared house", ownership_type="own", pool=True), users["alice"], "personal"
    )
    listed = list_homes(
        users["bob"], "personal"
    )  # non-admin member should still SEE it (read is open)
    assert any(h["id"] == created["id"] for h in listed)


def test_member_with_pool_edit_grant_can_create_pool_home(users):
    from services import auth_service

    auth_service.update_user(users["bob"]["id"], {"pool_edit": ["household"]})
    bob = auth_service.get_user_by_id(users["bob"]["id"])
    created = create_home(
        HomeCreate(name="Shared house 2", ownership_type="own", pool=True), bob, "personal"
    )
    assert created["name"] == "Shared house 2"


def test_bulk_delete_reports_per_item_failure(users):
    created = create_home(HomeCreate(name="Real", ownership_type="rent"), users["bob"], "personal")
    result = bulk_delete_homes(
        BulkDeleteRequest(ids=[created["id"], "11111111-1111-1111-1111-111111111111"]),
        users["bob"],
        "personal",
    )
    assert result["deleted"] == [created["id"]]
    assert len(result["failed"]) == 1
    assert result["failed"][0]["id"] == "11111111-1111-1111-1111-111111111111"


def test_get_home_items_finds_tagged_task(users):
    from services import task_service

    home = create_home(
        HomeCreate(name="Tagged house", ownership_type="rent"), users["bob"], "personal"
    )
    task_service.add_task(users["bob"]["name"], {"title": "Fix the sink", "tags": [home["tag"]]})

    result = get_home_items(home["id"], False, users["bob"], "personal")
    titles = [item["title"] for item in result["items"]]
    assert "Fix the sink" in titles


def test_get_home_items_404_across_users(users):
    bobs_home = create_home(
        HomeCreate(name="Bob's place", ownership_type="rent"), users["bob"], "personal"
    )
    with pytest.raises(HTTPException) as exc:
        get_home_items(bobs_home["id"], False, users["alice"], "personal")
    assert exc.value.status_code == 404


def test_get_home_items_finds_tagged_pool_task_end_to_end(users):
    """The one thing the plan explicitly says not to trust by inference
    alone: a pool home's tag, applied to a POOL-scoped task (owned by the
    _household pseudo-user, not either real user), must come back from the
    aggregation endpoint — household's own search provider is what makes
    this work, not anything homes-specific."""
    from services import task_service

    home = create_home(
        HomeCreate(name="Household home", ownership_type="own", pool=True),
        users["alice"],
        "personal",
    )
    task_service.add_task("_household", {"title": "Mow the lawn", "tags": [home["tag"]]})

    result = get_home_items(home["id"], True, users["bob"], "personal")
    titles = [item["title"] for item in result["items"]]
    assert "Mow the lawn" in titles


def test_convert_home_to_pool_moves_it_and_preserves_tag(users):
    """Owner ask, 2026-09-18: a personal home needs a way to become a
    shared household home after the fact, not only at creation time."""
    home = create_home(
        HomeCreate(name="Alice's place", ownership_type="rent"), users["alice"], "personal"
    )
    original_tag = home["tag"]

    converted = convert_home_to_pool(home["id"], users["alice"], "personal")

    assert converted["id"] == home["id"]
    assert converted["tag"] == original_tag
    assert converted["_owner"] == "household"
    # No longer in Alice's own personal store...
    with pytest.raises(HTTPException):
        get_home(home["id"], False, users["alice"], "personal")
    # ...but visible to everyone (Bob included) via the pool.
    listed = list_homes(users["bob"], "personal")
    assert any(h["id"] == home["id"] and h.get("_owner") == "household" for h in listed)


def test_convert_home_to_pool_requires_pool_edit(users):
    home = create_home(
        HomeCreate(name="Bob's place", ownership_type="rent"), users["bob"], "personal"
    )
    with pytest.raises(HTTPException) as exc:
        convert_home_to_pool(home["id"], users["bob"], "personal")
    assert exc.value.status_code == 403
    # Untouched — still in Bob's own store.
    assert get_home(home["id"], False, users["bob"], "personal") is not None


def test_convert_home_to_pool_404_when_missing(users):
    with pytest.raises(HTTPException) as exc:
        convert_home_to_pool("11111111-1111-1111-1111-111111111111", users["alice"], "personal")
    assert exc.value.status_code == 404


def test_convert_home_to_pool_404_when_belongs_to_another_user(users):
    bobs_home = create_home(
        HomeCreate(name="Bob's place", ownership_type="rent"), users["bob"], "personal"
    )
    with pytest.raises(HTTPException) as exc:
        convert_home_to_pool(bobs_home["id"], users["alice"], "personal")
    assert exc.value.status_code == 404


def test_update_home_after_convert_to_pool_requires_pool_flag(users):
    """Real bug found live 2026-09-18: HomeDetail.jsx's own save() never
    sent `pool: true` in the PATCH body after a home had been converted to
    the household pool, so it kept looking in (and 404ing against) the
    caller's own personal store — the exact store the home no longer lived
    in. `HomeUpdate.pool` genuinely defaults False (matching HomeCreate's
    own default), so a caller must say which store to look in on update
    the same way it must on create; this test locks in that contract."""
    home = create_home(
        HomeCreate(name="Shared house", ownership_type="own", pool=True), users["alice"], "personal"
    )

    with pytest.raises(HTTPException) as exc:
        update_home(home["id"], HomeUpdate(name="Renamed"), users["alice"], "personal")
    assert exc.value.status_code == 404

    result = update_home(
        home["id"], HomeUpdate(name="Renamed", pool=True), users["alice"], "personal"
    )
    assert result["name"] == "Renamed"
