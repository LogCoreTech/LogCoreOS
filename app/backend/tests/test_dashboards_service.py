"""Tests for dashboards_service + dashboard_blocks.render — CRUD, access
resolution, floor-of-one delete, and the share_underlying_data security
matrix (the highest-consequence code path in the Dashboards feature)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import assets_service as assets_svc
from services import auth_service, contacts_service
from services import dashboard_templates_service as tmpl_svc
from services import dashboards_service as svc
from services.dashboard_blocks._collections import resolve_collection
from services.dashboard_blocks._contacts import resolve_contacts_list
from services.dashboard_blocks.registry import REGISTRY, BlockRenderCtx, _load_all_resolvers
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


# ---------------------------------------------------------------------------
# m011 — grid rescale (12 cols/80px rows -> 36 cols/24px rows) migration
# ---------------------------------------------------------------------------


def test_m011_rescales_existing_dashboard_grid_units(users, brain):
    from migrations.runner import m011_rescale_dashboard_grid_units

    d = svc.create_dashboard("Alice", "personal", "Alice", "Old Board")
    old_block = {
        "id": "block-1",
        "type": "top3_tasks",
        "config": {},
        "layout": {"lg": {"x": 4, "y": 0, "w": 4, "h": 3}, "sm": {"x": 0, "y": 0, "w": 2, "h": 3}},
    }
    svc.update_dashboard("Alice", "personal", d["id"], {"blocks": [old_block]})

    m011_rescale_dashboard_grid_units(brain)

    rescaled = svc.get_dashboard("Alice", d["id"], "personal")
    block = rescaled["blocks"][0]
    assert block["layout"]["lg"] == {"x": 12, "y": 0, "w": 12, "h": 9}
    assert block["layout"]["sm"] == {"x": 0, "y": 0, "w": 6, "h": 9}

    # Not idempotent by design (documented, accepted risk — see docs/MEMORY.md
    # and the plan this shipped from): a second run scales again. Asserting
    # this explicitly so a future idempotency guard is a deliberate change,
    # not a silent behavior shift this test would otherwise mask.
    m011_rescale_dashboard_grid_units(brain)
    twice = svc.get_dashboard("Alice", d["id"], "personal")
    assert twice["blocks"][0]["layout"]["lg"]["w"] == 36


# ---------------------------------------------------------------------------
# m012 — mobile grid rescale (cols.sm 2 -> 12), normalize not multiply
# ---------------------------------------------------------------------------


def test_m012_normalizes_mobile_layout_regardless_of_prior_width(users, brain):
    from migrations.runner import m012_rescale_dashboard_mobile_grid_units

    d = svc.create_dashboard("Alice", "personal", "Alice", "Board")
    # Two blocks with different sm-width provenance: one still at the
    # pre-m011 value (w:2), one already blindly ×3'd BY m011 (w:6) — m012
    # must normalize both to the same w:12, since neither value was ever
    # actually meaningful (sm was never read at render time until now).
    blocks = [
        {
            "id": "block-1",
            "type": "top3_tasks",
            "config": {},
            "layout": {
                "lg": {"x": 0, "y": 0, "w": 12, "h": 9},
                "sm": {"x": 0, "y": 0, "w": 2, "h": 9},
            },
        },
        {
            "id": "block-2",
            "type": "due_today",
            "config": {},
            "layout": {
                "lg": {"x": 12, "y": 0, "w": 12, "h": 9},
                "sm": {"x": 0, "y": 9, "w": 6, "h": 9},
            },
        },
    ]
    svc.update_dashboard("Alice", "personal", d["id"], {"blocks": blocks})

    m012_rescale_dashboard_mobile_grid_units(brain)

    result = svc.get_dashboard("Alice", d["id"], "personal")
    b1, b2 = result["blocks"]
    assert b1["layout"]["sm"] == {"x": 0, "y": 0, "w": 12, "h": 9}
    assert b2["layout"]["sm"] == {"x": 0, "y": 9, "w": 12, "h": 9}
    # lg untouched — this migration only concerns the sm breakpoint
    assert b1["layout"]["lg"] == {"x": 0, "y": 0, "w": 12, "h": 9}
    assert b2["layout"]["lg"] == {"x": 12, "y": 0, "w": 12, "h": 9}

    # Idempotent by design (unlike m011's multiply) — a second run is a no-op
    m012_rescale_dashboard_mobile_grid_units(brain)
    twice = svc.get_dashboard("Alice", d["id"], "personal")
    assert twice["blocks"][0]["layout"]["sm"] == {"x": 0, "y": 0, "w": 12, "h": 9}


# ---------------------------------------------------------------------------
# Dashboard Templates — CRUD, live block-set sync, per-instance layout
# independence, $subject substitution
# ---------------------------------------------------------------------------


def _contact(owner="Alice", name="Acme Co"):
    return contacts_service.create_contact(owner, "personal", {"name": name}, owner)


def test_template_crud_and_reference_guard(users):
    t = tmpl_svc.create_template(
        {"label": "Client Overview", "subject_type": "contact", "blocks": []},
        owner=tmpl_svc.GLOBAL_OWNER,
    )
    assert t["subject_type"] == "contact"
    assert tmpl_svc.get_template_by_id(t["id"])["label"] == "Client Overview"

    contact = _contact()
    svc.create_dashboard("Alice", "personal", "Alice", "Spare")  # keep floor-of-one satisfied below
    d = svc.create_dashboard(
        "Alice", "personal", "Alice", "Acme", template_id=t["id"], subject_id=contact["id"]
    )
    assert tmpl_svc.template_reference_count(t["id"]) == 1
    with pytest.raises(ValueError):
        tmpl_svc.delete_template(t["id"])

    svc.delete_dashboard("Alice", "personal", d["id"])
    assert tmpl_svc.template_reference_count(t["id"]) == 0
    assert tmpl_svc.delete_template(t["id"]) is True


def test_create_from_template_requires_subject_when_declared(users):
    t = tmpl_svc.create_template({"label": "Needs Subject", "subject_type": "asset"}, owner="Alice")
    with pytest.raises(ValueError):
        svc.create_dashboard("Alice", "personal", "Alice", "Missing Subject", template_id=t["id"])


def test_create_from_template_seeds_blocks_with_stacked_layout(users):
    t = tmpl_svc.create_template(
        {
            "label": "Two Blocks",
            "blocks": [
                {"type": "top3_tasks", "config": {}},
                {"type": "due_today", "config": {}},
            ],
        },
        owner="Alice",
    )
    d = svc.create_dashboard("Alice", "personal", "Alice", "From Template", template_id=t["id"])
    assert d["template_id"] == t["id"]
    assert [b["type"] for b in d["blocks"]] == ["top3_tasks", "due_today"]
    # Second slot stacked below the first, not overlapping it.
    assert (
        d["blocks"][1]["layout"]["lg"]["y"]
        >= d["blocks"][0]["layout"]["lg"]["y"] + d["blocks"][0]["layout"]["lg"]["h"]
    )


def test_template_sync_adds_and_removes_blocks_on_read(users):
    t = tmpl_svc.create_template(
        {"label": "Evolving", "blocks": [{"type": "top3_tasks", "config": {}}]}, owner="Alice"
    )
    d = svc.create_dashboard("Alice", "personal", "Alice", "Instance", template_id=t["id"])
    assert len(d["blocks"]) == 1

    tmpl_svc.update_template(
        t["id"], {"blocks": [*t["blocks"], {"type": "due_today", "config": {}}]}
    )
    found = svc.find_dashboard("Alice", "member", False, "personal", d["id"])
    assert [b["type"] for b in found["dashboard"]["blocks"]] == ["top3_tasks", "due_today"]

    tmpl_svc.update_template(t["id"], {"blocks": [{"type": "due_today", "config": {}}]})
    found = svc.find_dashboard("Alice", "member", False, "personal", d["id"])
    assert [b["type"] for b in found["dashboard"]["blocks"]] == ["due_today"]


def test_template_sync_preserves_per_instance_layout_customization(users):
    t = tmpl_svc.create_template(
        {"label": "Layout Test", "blocks": [{"type": "top3_tasks", "config": {}}]}, owner="Alice"
    )
    d = svc.create_dashboard("Alice", "personal", "Alice", "Instance", template_id=t["id"])
    slot_id = d["blocks"][0]["id"]

    custom_layout = {
        "lg": {"x": 6, "y": 3, "w": 9, "h": 6},
        "sm": {"x": 0, "y": 0, "w": 12, "h": 6},
    }
    svc.update_dashboard(
        "Alice",
        "personal",
        d["id"],
        {"blocks": [{"id": slot_id, "type": "top3_tasks", "config": {}, "layout": custom_layout}]},
    )

    # Template gains a second block -> sync must add it without disturbing slot 1's layout.
    tmpl_svc.update_template(
        t["id"], {"blocks": [*t["blocks"], {"type": "due_today", "config": {}}]}
    )
    found = svc.find_dashboard("Alice", "member", False, "personal", d["id"])
    blocks = found["dashboard"]["blocks"]
    assert blocks[0]["layout"] == custom_layout
    assert blocks[1]["type"] == "due_today"


def test_templated_dashboard_patch_is_layout_only(users):
    t = tmpl_svc.create_template(
        {"label": "Locked Set", "blocks": [{"type": "top3_tasks", "config": {}}]}, owner="Alice"
    )
    d = svc.create_dashboard("Alice", "personal", "Alice", "Instance", template_id=t["id"])
    slot_id = d["blocks"][0]["id"]

    # Attempt to retype/reconfigure/add a block via the normal blocks PATCH —
    # only the layout change should stick; type/config/set membership are
    # template-controlled regardless of what the client sends.
    tampered = svc.update_dashboard(
        "Alice",
        "personal",
        d["id"],
        {
            "blocks": [
                {
                    "id": slot_id,
                    "type": "ai_usage_overview",
                    "config": {"hacked": True},
                    "layout": {
                        "lg": {"x": 1, "y": 1, "w": 8, "h": 4},
                        "sm": {"x": 0, "y": 0, "w": 12, "h": 9},
                    },
                },
                {"id": "not-a-real-slot", "type": "due_today", "config": {}, "layout": {}},
            ]
        },
    )
    assert len(tampered["blocks"]) == 1
    assert tampered["blocks"][0]["type"] == "top3_tasks"
    assert tampered["blocks"][0]["config"] == {}
    assert tampered["blocks"][0]["layout"]["lg"] == {"x": 1, "y": 1, "w": 8, "h": 4}


def test_subject_substitution_renders_each_instances_own_contact(users):
    t = tmpl_svc.create_template(
        {
            "label": "Contact Overview",
            "subject_type": "contact",
            "blocks": [{"type": "linked_deals", "config": {"contact_id": "$subject"}}],
        },
        owner="Alice",
    )
    acme = _contact(name="Acme Co")
    globex = _contact(name="Globex Inc")
    d1 = svc.create_dashboard(
        "Alice", "personal", "Alice", "Acme Dash", template_id=t["id"], subject_id=acme["id"]
    )
    d2 = svc.create_dashboard(
        "Alice", "personal", "Alice", "Globex Dash", template_id=t["id"], subject_id=globex["id"]
    )

    r1 = render_block(d1, d1["blocks"][0], "Alice", "member", False, "personal", "edit")
    r2 = render_block(d2, d2["blocks"][0], "Alice", "member", False, "personal", "edit")
    assert r1.ok is True and r1.data["contact_name"] == "Acme Co"
    assert r2.ok is True and r2.data["contact_name"] == "Globex Inc"


def test_subject_substitution_locked_when_no_subject_set_yet(users):
    t = tmpl_svc.create_template(
        {
            "label": "No Subject Yet",
            "subject_type": "contact",
            "blocks": [{"type": "linked_deals", "config": {"contact_id": "$subject"}}],
        },
        owner="Alice",
    )
    contact = _contact()
    d = svc.create_dashboard(
        "Alice", "personal", "Alice", "Dash", template_id=t["id"], subject_id=contact["id"]
    )
    svc.set_subject("Alice", "personal", d["id"], None)
    d = svc.get_dashboard("Alice", d["id"], "personal")
    result = render_block(d, d["blocks"][0], "Alice", "member", False, "personal", "edit")
    assert result.ok is False
    assert result.locked_reason == "no_subject"


def test_set_subject_then_detach_stops_future_sync(users):
    t = tmpl_svc.create_template(
        {"label": "Detachable", "blocks": [{"type": "top3_tasks", "config": {}}]}, owner="Alice"
    )
    d = svc.create_dashboard("Alice", "personal", "Alice", "Dash", template_id=t["id"])

    detached = svc.detach_template("Alice", "personal", d["id"])
    assert detached["template_id"] is None
    assert len(detached["blocks"]) == 1  # kept as-is, now independent

    # Template changes no longer propagate once detached.
    tmpl_svc.update_template(
        t["id"], {"blocks": [*t["blocks"], {"type": "due_today", "config": {}}]}
    )
    found = svc.find_dashboard("Alice", "member", False, "personal", d["id"])
    assert len(found["dashboard"]["blocks"]) == 1


# ---------------------------------------------------------------------------
# Collection block — generic source/view/action (2026-08-07)
# ---------------------------------------------------------------------------


def _ctx(viewer="Alice", config=None, workspace="personal", is_admin=False, owner="Alice"):
    return BlockRenderCtx(
        viewer=viewer,
        viewer_role="member",
        is_admin=is_admin,
        workspace=workspace,
        config=config or {},
        dashboard_owner=owner,
    )


def test_asset_links_contact_helper(users):
    t = assets_svc.create_template(
        {"key": "listing1", "label": "Listing", "fields": [{"key": "client", "type": "contact"}]},
        owner="Alice",
    )
    linked = assets_svc.create_asset(
        "Alice",
        {"template_id": t["id"], "name": "House", "fields": {"client": "c-1"}},
        created_by="Alice",
    )
    unlinked = assets_svc.create_asset(
        "Alice", {"template_id": t["id"], "name": "Other", "fields": {}}, created_by="Alice"
    )
    assert assets_svc.asset_links_contact(linked, t, "c-1") is True
    assert assets_svc.asset_links_contact(linked, t, "c-2") is False
    assert assets_svc.asset_links_contact(unlinked, t, "c-1") is False
    assert (
        assets_svc.asset_links_contact(linked, {"fields": []}, "c-1") is False
    )  # no contact-type fields at all


def test_collection_no_template_id_locks(users):
    result = resolve_collection(_ctx(config={}))
    assert result.ok is False
    assert result.locked_reason == "not_found"


def test_collection_filters_by_template_and_excludes_archived(users):
    t = assets_svc.create_template(
        {
            "key": "listing2",
            "label": "Listing",
            "fields": [
                {"key": "client", "type": "contact"},
                {"key": "status", "type": "select", "options": ["Active", "Sold"]},
            ],
        },
        owner="Alice",
    )
    other_t = assets_svc.create_template(
        {"key": "vehicle2", "label": "Vehicle", "fields": []}, owner="Alice"
    )
    keep = assets_svc.create_asset(
        "Alice",
        {"template_id": t["id"], "name": "123 Main St", "fields": {"status": "Active"}},
        created_by="Alice",
    )
    archived = assets_svc.create_asset(
        "Alice",
        {"template_id": t["id"], "name": "Archived House", "fields": {"status": "Sold"}},
        created_by="Alice",
    )
    assets_svc.set_archived("Alice", archived["id"], True)
    assets_svc.create_asset(
        "Alice", {"template_id": other_t["id"], "name": "Truck"}, created_by="Alice"
    )

    result = resolve_collection(_ctx(config={"template_id": t["id"], "display_fields": ["status"]}))
    assert result.ok is True
    assert [r["id"] for r in result.data["rows"]] == [keep["id"]]
    assert result.data["rows"][0]["fields"]["status"] == "Active"
    assert result.data["count"] == 1


def test_collection_filters_by_link_contact_id(users):
    t = assets_svc.create_template(
        {"key": "listing3", "label": "Listing", "fields": [{"key": "client", "type": "contact"}]},
        owner="Alice",
    )
    mine = assets_svc.create_asset(
        "Alice",
        {"template_id": t["id"], "name": "For Acme", "fields": {"client": "c-acme"}},
        created_by="Alice",
    )
    assets_svc.create_asset(
        "Alice",
        {"template_id": t["id"], "name": "For Globex", "fields": {"client": "c-globex"}},
        created_by="Alice",
    )

    result = resolve_collection(_ctx(config={"template_id": t["id"], "link_contact_id": "c-acme"}))
    assert [r["id"] for r in result.data["rows"]] == [mine["id"]]


def test_collection_status_options_from_select_field(users):
    t = assets_svc.create_template(
        {
            "key": "listing4",
            "label": "Listing",
            "fields": [
                {"key": "status", "type": "select", "options": ["Toured", "Offer Made", "Passed"]}
            ],
        },
        owner="Alice",
    )
    a = assets_svc.create_asset(
        "Alice",
        {"template_id": t["id"], "name": "456 Oak Ave", "fields": {"status": "Toured"}},
        created_by="Alice",
    )

    result = resolve_collection(
        _ctx(config={"template_id": t["id"], "status_field": "status", "view": "kanban"})
    )
    assert result.data["status_options"] == ["Toured", "Offer Made", "Passed"]
    assert result.data["rows"][0]["status_value"] == "Toured"
    assert result.data["rows"][0]["id"] == a["id"]
    assert result.data["view"] == "kanban"


def test_collection_respects_dashboard_subject_via_sentinel(users):
    """End-to-end through render_block: a templated dashboard's collection
    block using the $subject sentinel resolves to that instance's own
    contact, same as any other $subject-aware block."""
    t = assets_svc.create_template(
        {
            "key": "viewed1",
            "label": "Property Viewed",
            "fields": [{"key": "buyer", "type": "contact"}],
        },
        owner="Alice",
    )
    acme_contact = contacts_service.create_contact(
        "Alice", "personal", {"name": "Acme Buyer"}, "Alice"
    )
    globex_contact = contacts_service.create_contact(
        "Alice", "personal", {"name": "Globex Buyer"}, "Alice"
    )
    house_a = assets_svc.create_asset(
        "Alice",
        {"template_id": t["id"], "name": "House A", "fields": {"buyer": acme_contact["id"]}},
        created_by="Alice",
    )
    assets_svc.create_asset(
        "Alice",
        {"template_id": t["id"], "name": "House B", "fields": {"buyer": globex_contact["id"]}},
        created_by="Alice",
    )

    dash_tmpl = tmpl_svc.create_template(
        {
            "label": "Buyer Client",
            "subject_type": "contact",
            "blocks": [
                {
                    "type": "collection",
                    "config": {"template_id": t["id"], "link_contact_id": "$subject"},
                }
            ],
        },
        owner="Alice",
    )
    d = svc.create_dashboard(
        "Alice",
        "personal",
        "Alice",
        "Acme Buyer Dash",
        template_id=dash_tmpl["id"],
        subject_id=acme_contact["id"],
    )
    result = render_block(d, d["blocks"][0], "Alice", "member", False, "personal", "edit")
    assert result.ok is True
    assert [r["id"] for r in result.data["rows"]] == [house_a["id"]]


# ---------------------------------------------------------------------------
# Contacts List block — new block type (2026-08-15), for block-embedded
# action buttons ("Assets... update statuses" / "Notes... open" examples)
# ---------------------------------------------------------------------------


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
