"""Router-level tests for module_packages/dashboard/backend/router.py — the
first-ever HTTP-layer coverage of this router (dashboards_service.py's own
CRUD/access logic is already covered by tests/test_dashboards_service.py;
this file is about the router's own body logic: floor-of-one delete
protection, pool-create admin gating, access-level gates on updates, and
404 handling).

Endpoint functions are called directly with a pre-resolved user dict and a
plain workspace string, matching this test suite's established convention
(see test_household_router.py/test_notes_router.py) — Depends(
_require_dashboards)/Depends(get_workspace) are bypassed the same way
Depends(require_admin) already is elsewhere; this file tests the endpoints'
own body logic, not the require_module dependency chain itself (untested
anywhere in this suite today, a pre-existing, systemic gap this conversion
isn't scoped to close)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.dashboard.backend.router import (
    DashboardCreate,
    DashboardUpdate,
    create_dashboard,
    delete_dashboard,
    get_dashboard,
    list_dashboards,
    update_dashboard,
)


@pytest.fixture()
def users(brain):
    from services import auth_service

    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_create_and_list_dashboards(users):
    create_dashboard(DashboardCreate(name="Home"), users["alice"], "personal")

    result = list_dashboards(users["alice"], "personal")

    assert any(d["name"] == "Home" for d in result["items"])


def test_get_dashboard_404_when_missing(users):
    with pytest.raises(HTTPException) as exc:
        get_dashboard("nope", users["alice"], "personal")
    assert exc.value.status_code == 404


def test_get_dashboard_returns_owner_and_access(users):
    created = create_dashboard(DashboardCreate(name="Budget"), users["alice"], "personal")

    result = get_dashboard(created["id"], users["alice"], "personal")

    assert result["_owner"] == "own"
    assert result["_access"] == "edit"


def test_update_dashboard_renames(users):
    created = create_dashboard(DashboardCreate(name="Old Name"), users["alice"], "personal")

    result = update_dashboard(
        created["id"], DashboardUpdate(name="New Name"), users["alice"], "personal"
    )

    assert result["name"] == "New Name"


def test_delete_dashboard(users):
    create_dashboard(DashboardCreate(name="First"), users["alice"], "personal")
    second = create_dashboard(DashboardCreate(name="Second"), users["alice"], "personal")

    delete_dashboard(second["id"], users["alice"], "personal")

    assert not any(d["id"] == second["id"] for d in list_dashboards(users["alice"], "personal")["items"])


def test_delete_last_dashboard_rejected_409(users):
    """LogCore always keeps a user at least one landing page — the
    floor-of-one delete protection dashboards_service.delete_dashboard()
    enforces, surfaced here as a real 409 through the router."""
    only = create_dashboard(DashboardCreate(name="Only One"), users["bob"], "personal")

    with pytest.raises(HTTPException) as exc:
        delete_dashboard(only["id"], users["bob"], "personal")
    assert exc.value.status_code == 409


def test_pool_dashboard_creation_requires_admin(users):
    with pytest.raises(HTTPException) as exc:
        create_dashboard(DashboardCreate(name="Household", pool=True), users["bob"], "personal")
    assert exc.value.status_code == 403


def test_pool_dashboard_creation_by_admin_is_edit_accessible_to_admin_only_by_default(users):
    """Unlike pool Notes/Tasks (workspace-visible by default), a pool
    dashboard's non-admin access comes only from an explicit `contributors`
    grant (dashboards_service._contributor_access) — a plain member sees
    nothing until one is added. Confirmed real design, not a bug: admins
    always get edit on any pool dashboard regardless."""
    created = create_dashboard(DashboardCreate(name="Shared", pool=True), users["alice"], "personal")

    admin_view = list_dashboards(users["alice"], "personal")
    assert any(d["name"] == "Shared" for d in admin_view["items"])

    member_view = list_dashboards(users["bob"], "personal")
    assert not any(d["id"] == created["id"] for d in member_view["items"])
