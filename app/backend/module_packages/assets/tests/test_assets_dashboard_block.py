"""Tests for the Collection block — moved from tests/test_dashboards_service.py
when assets/ converted (2026-08-27), since resolve_collection() folded into
module_packages/assets/backend/dashboard_block.py (from the old, separate
dashboard_blocks/_collections.py, gaining module="assets" gating for the
first time). Deliberately Assets-only for v1, per the resolver's own
docstring, which anticipates future generalization to other record types."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from services import assets_service as assets_svc
from services import auth_service, contacts_service
from services import dashboard_templates_service as tmpl_svc
from services import dashboards_service as svc
from services.dashboard_blocks.registry import BlockRenderCtx, _load_all_resolvers
from services.dashboard_blocks.render import render_block

_load_all_resolvers()


@pytest.fixture()
def users(brain):
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def _ctx(viewer="Alice", config=None, workspace="personal", is_admin=False, owner="Alice"):
    return BlockRenderCtx(
        viewer=viewer,
        viewer_role="member",
        is_admin=is_admin,
        workspace=workspace,
        config=config or {},
        dashboard_owner=owner,
    )


def test_collection_no_template_id_locks(users):
    from module_packages.assets.backend.dashboard_block import resolve_collection

    result = resolve_collection(_ctx(config={}))
    assert result.ok is False
    assert result.locked_reason == "not_found"


def test_collection_filters_by_template_and_excludes_archived(users):
    from module_packages.assets.backend.dashboard_block import resolve_collection

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
    from module_packages.assets.backend.dashboard_block import resolve_collection

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
    from module_packages.assets.backend.dashboard_block import resolve_collection

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
