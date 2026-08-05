"""Tests for dashboards_service + dashboard_blocks.render — CRUD, access
resolution, floor-of-one delete, and the share_underlying_data security
matrix (the highest-consequence code path in the Dashboards feature)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import auth_service
from services import dashboards_service as svc
from services.dashboard_blocks.registry import BlockRenderCtx, REGISTRY, _load_all_resolvers
from services.dashboard_blocks.render import render_block

_load_all_resolvers()


@pytest.fixture()
def users(brain):
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_create_and_list(users):
    d = svc.create_dashboard("Alice", "personal", "Alice", "My Board", "🎯")
    assert d["name"] == "My Board"
    assert d["owner"] == "Alice"
    assert d["share_underlying_data"] is False
    items = svc.list_visible_dashboards("Alice", "member", False, "personal")
    assert len(items) == 1
    assert items[0]["_access"] == "edit"


def test_bob_cannot_see_alices_unshared_dashboard(users):
    svc.create_dashboard("Alice", "personal", "Alice", "Private")
    items = svc.list_visible_dashboards("Bob", "member", False, "personal")
    assert items == []


def test_share_handshake_read_access(users):
    d = svc.create_dashboard("Alice", "personal", "Alice", "Shared Board")
    svc.update_access(
        "Alice", "personal", d["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    # Not accepted yet -> Bob doesn't see it
    found = svc.find_dashboard("Bob", "member", False, "personal", d["id"])
    assert found is None

    svc.respond_to_share("Bob", "Alice", "personal", d["id"], True)
    found = svc.find_dashboard("Bob", "member", False, "personal", d["id"])
    assert found is not None
    assert found["access"] == "read"


def test_hidden_from_beats_shares(users):
    d = svc.create_dashboard("Alice", "personal", "Alice", "Board")
    svc.update_access(
        "Alice",
        "personal",
        d["id"],
        shared_with=[{"target": "Bob", "access": "edit"}],
        hidden_from=["Bob"],
        by="Alice",
    )
    svc.respond_to_share("Bob", "Alice", "personal", d["id"], True)
    found = svc.find_dashboard("Bob", "member", False, "personal", d["id"])
    assert found is None


def test_floor_of_one_blocks_delete(users):
    d = svc.create_dashboard("Alice", "personal", "Alice", "Only One")
    with pytest.raises(ValueError, match="floor_of_one"):
        svc.delete_dashboard("Alice", "personal", d["id"])
    # Still there
    assert svc.get_dashboard("Alice", d["id"], "personal") is not None


def test_delete_allowed_when_multiple_exist(users):
    d1 = svc.create_dashboard("Alice", "personal", "Alice", "One")
    svc.create_dashboard("Alice", "personal", "Alice", "Two")
    svc.delete_dashboard("Alice", "personal", d1["id"])
    assert svc.get_dashboard("Alice", d1["id"], "personal") is None


def test_resolve_default_dashboard_self_healing(users):
    d = svc.create_dashboard("Alice", "personal", "Alice", "Solo")
    resolved = svc.resolve_default_dashboard_id("Alice", "member", False, "personal", None)
    assert resolved == d["id"]

    # A stale saved default that no longer resolves falls back correctly
    resolved2 = svc.resolve_default_dashboard_id(
        "Alice", "member", False, "personal", "does-not-exist"
    )
    assert resolved2 == d["id"]


def test_pool_dashboard_contributor_access(users):
    d = svc.create_dashboard("_household", "personal", "Alice", "Family Board")
    # No contributor grant yet -> Bob can't see it
    found = svc.find_dashboard("Bob", "member", False, "personal", d["id"])
    assert found is None

    svc.update_access(
        "_household",
        "personal",
        d["id"],
        contributors=[{"target": "Bob", "access": "contribute"}],
        by="Alice",
    )
    found = svc.find_dashboard("Bob", "member", False, "personal", d["id"])
    assert found is not None
    assert found["access"] == "contribute"

    # Admin always gets edit on pool dashboards regardless of contributors
    admin_found = svc.find_dashboard("Alice", "admin", True, "personal", d["id"])
    assert admin_found["access"] == "edit"


# ---------------------------------------------------------------------------
# share_underlying_data — the security matrix from the implementation plan
# ---------------------------------------------------------------------------


def _owner_scoped_block(block_type="top3_tasks"):
    return {"id": "b1", "type": block_type, "config": {"scope": "owner"}, "layout": {}}


def test_no_dashboard_access_locked_regardless_of_toggle(users):
    dashboard = {"owner": "Alice", "share_underlying_data": True}
    block = _owner_scoped_block()
    result = render_block(dashboard, block, "Bob", "member", False, "personal", None)
    assert result.ok is False


def test_toggle_off_stays_locked(users):
    dashboard = {"owner": "Alice", "share_underlying_data": False}
    block = _owner_scoped_block()
    result = render_block(dashboard, block, "Bob", "member", False, "personal", "read")
    assert result.ok is False
    assert result.locked_reason == "no_access"


def test_toggle_on_renders_as_owner(users):
    dashboard = {"owner": "Alice", "share_underlying_data": True}
    block = _owner_scoped_block()
    result = render_block(dashboard, block, "Bob", "member", False, "personal", "read")
    assert result.ok is True
    assert "tasks" in result.data


def test_toggle_on_but_owner_lost_access_stays_locked(users):
    # Owner references a nonexistent user -> auth_service.get_user_by_name is
    # None inside render_block -> fail closed for everyone, including a
    # dashboard-access-holding viewer.
    dashboard = {"owner": "GhostUser", "share_underlying_data": True}
    block = _owner_scoped_block()
    result = render_block(dashboard, block, "Bob", "member", False, "personal", "read")
    assert result.ok is False


def test_admin_only_block_locked_for_non_admin_even_with_toggle_if_owner_not_admin(users):
    dashboard = {"owner": "Bob", "share_underlying_data": True}  # Bob is a non-admin owner
    block = {"id": "b2", "type": "ai_usage_overview", "config": {}, "layout": {}}
    # Some other non-admin viewer with dashboard read access
    auth_service.create_user("carol@example.com", "password123", "Carol")
    result = render_block(dashboard, block, "Carol", "member", False, "personal", "read")
    assert result.ok is False
    assert result.locked_reason in ("admin_only", "no_access")


def test_admin_only_block_renders_when_owner_is_admin_and_toggle_on(users):
    dashboard = {"owner": "Alice", "share_underlying_data": True}  # Alice is admin
    block = {"id": "b3", "type": "ai_usage_overview", "config": {}, "layout": {}}
    auth_service.create_user("carol@example.com", "password123", "Carol")
    result = render_block(dashboard, block, "Carol", "member", False, "personal", "read")
    assert result.ok is True


def test_viewer_is_owner_toggle_never_consulted(users):
    dashboard = {"owner": "Alice", "share_underlying_data": False}
    block = _owner_scoped_block()
    result = render_block(dashboard, block, "Alice", "member", False, "personal", "edit")
    assert result.ok is True


def test_viewer_scope_default_always_succeeds_without_toggle(users):
    dashboard = {"owner": "Alice", "share_underlying_data": False}
    block = {"id": "b4", "type": "top3_tasks", "config": {"scope": "viewer"}, "layout": {}}
    result = render_block(dashboard, block, "Bob", "member", False, "personal", None)
    assert result.ok is True
