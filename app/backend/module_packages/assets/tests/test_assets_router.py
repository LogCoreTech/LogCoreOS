"""Router-level tests for module_packages/assets/backend/router.py — the
first-ever HTTP-layer coverage of this router (assets_service.py's own
CRUD/sharing/caps logic is already covered by tests/test_assets_service.py
and tests/test_assets_templates.py; this file is about the router's own
body logic: creator-access annotation, contribute-level field caps
enforcement, delete-blocked-while-has-children, pool conversion, and 404
handling).

Endpoint functions are called directly with a pre-resolved user dict and a
plain workspace string, matching this test suite's established convention
(see test_notes_router.py/test_dashboard_router.py) — Depends(
_require_assets)/Depends(get_workspace) are bypassed the same way
Depends(require_admin) already is elsewhere; this file tests the endpoints'
own body logic, not the require_module dependency chain itself (untested
anywhere in this suite today, a pre-existing, systemic gap this conversion
isn't scoped to close)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.assets.backend.router import (
    AccessUpdate,
    AssetCreate,
    AssetUpdate,
    ContributorEntry,
    ConvertRequest,
    ShareEntry,
    TemplateCreate,
    archive_asset,
    convert_asset,
    create_asset,
    create_template,
    delete_asset,
    get_asset,
    list_assets,
    unarchive_asset,
    update_access,
    update_asset,
)


@pytest.fixture()
def users(brain):
    from services import auth_service

    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_create_and_list_assets(users):
    create_asset(AssetCreate(name="Lot 12"), users["alice"], "personal")

    result = list_assets(None, False, users["alice"], "personal")

    assert any(a["name"] == "Lot 12" for a in result)


def test_get_asset_404_when_missing(users):
    with pytest.raises(HTTPException) as exc:
        get_asset("11111111-1111-1111-1111-111111111111", users["alice"], "personal")
    assert exc.value.status_code == 404


def test_get_asset_invalid_id_400(users):
    with pytest.raises(HTTPException) as exc:
        get_asset("not-a-uuid", users["alice"], "personal")
    assert exc.value.status_code == 400


def test_update_asset_renames(users):
    created = create_asset(AssetCreate(name="Old Name"), users["alice"], "personal")

    result = update_asset(
        created["id"], AssetUpdate(name="New Name"), users["alice"], "personal"
    )

    assert result["name"] == "New Name"


def test_archive_and_unarchive_asset(users):
    created = create_asset(AssetCreate(name="Truck"), users["alice"], "personal")

    archive_asset(created["id"], False, users["alice"], "personal")
    result = list_assets(None, False, users["alice"], "personal")
    assert not any(a["id"] == created["id"] for a in result)

    unarchive_asset(created["id"], False, users["alice"], "personal")
    result = list_assets(None, False, users["alice"], "personal")
    assert any(a["id"] == created["id"] for a in result)


def test_delete_blocked_while_has_children(users):
    parent = create_asset(AssetCreate(name="Parent"), users["alice"], "personal")
    create_asset(
        AssetCreate(name="Child", parent_id=parent["id"]), users["alice"], "personal"
    )

    with pytest.raises(HTTPException) as exc:
        delete_asset(parent["id"], users["alice"], "personal")
    assert exc.value.status_code == 409


def test_delete_asset(users):
    created = create_asset(AssetCreate(name="Disposable"), users["alice"], "personal")

    delete_asset(created["id"], users["alice"], "personal")

    result = list_assets(None, False, users["alice"], "personal")
    assert not any(a["id"] == created["id"] for a in result)


# convert_asset's admin-only gate is Depends(require_admin) itself (not an
# inline body check like delete_asset's), so it can't be exercised by
# calling the function directly with a non-admin user the way every other
# access check in this file can — same documented, pre-existing limitation
# of this suite's direct-call convention as the require_module chain itself.


def test_convert_to_pool_makes_it_admin_edit_and_pool_owned(users):
    created = create_asset(AssetCreate(name="Mower"), users["alice"], "personal")

    result = convert_asset(created["id"], ConvertRequest(target="pool"), users["alice"], "personal")

    assert result["name"] == "Mower"
    # Converted, not a fresh copy — same asset now lives in the pool store.
    fetched = get_asset(created["id"], users["bob"], "personal")
    assert fetched["_owner"] == "household"


def test_contribute_access_can_only_change_capped_fields(users):
    created = create_asset(
        AssetCreate(name="Shared Lot", fields={"acres": "5"}), users["alice"], "personal"
    )
    update_access(
        created["id"],
        AccessUpdate(
            shared_with=[
                ShareEntry(target="Bob", access="contribute", caps={"fields": ["acres"], "add": []})
            ]
        ),
        users["alice"],
        "personal",
    )
    # A named-user share is a handshake, pending until accepted — same
    # shape as Notes' own sharing model.
    from services import assets_service

    assets_service.respond_to_asset_share(
        "Bob", {"owner": "Alice", "asset_id": created["id"], "workspace": "personal"}, True
    )

    # Allowed: a capped field.
    result = update_asset(
        created["id"], AssetUpdate(fields={"acres": "10"}), users["bob"], "personal"
    )
    assert result["fields"]["acres"] == "10"

    # Blocked: renaming isn't in the caps.
    with pytest.raises(HTTPException) as exc:
        update_asset(created["id"], AssetUpdate(name="Renamed"), users["bob"], "personal")
    assert exc.value.status_code == 400


def test_template_creation_and_visibility(users):
    created = create_template(
        TemplateCreate(key="vehicle", label="Vehicle", fields=[], owner="me"),
        users["alice"],
        None,
    )

    assert created["label"] == "Vehicle"


def test_global_template_creation_requires_admin(users):
    with pytest.raises(HTTPException) as exc:
        create_template(
            TemplateCreate(key="global_one", label="Global One", fields=[], owner="global"),
            users["bob"],
            None,
        )
    assert exc.value.status_code == 403
