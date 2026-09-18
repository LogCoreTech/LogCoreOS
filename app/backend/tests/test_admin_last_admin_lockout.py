"""Regression coverage for the last-admin lockout guard (2026-09-18,
TASKS.md backlog item): nothing previously stopped demoting or deleting the
only remaining admin, which would permanently lock an instance out of its
own admin functions (no other account could ever re-promote anyone). Covers
all three role/delete mutation paths: the current admin_users.py endpoints
(admin_update_user_role, admin_delete_user) and the older still-live legacy
role endpoint (update_user_role_legacy, PATCH /users/{id}/role).

The guard checks admin_count() at call time regardless of who the caller
is — the acting `current_user` dict in these direct-function-call tests is a
fabricated stand-in with a different id than the target (mirroring the
existing self-action checks' own shape), not a real second admin account,
since a real single-admin instance's only admin IS the only possible caller
of an admin-gated endpoint in practice; the guard is defense-in-depth against
any other path reaching these functions with a distinct actor."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException

from routers.auth import UpdateRoleRequest, admin_delete_user, admin_update_user_role
from routers.auth.admin_users import (
    DeletionExecuteRequest,
    RoleUpdateRequest,
    admin_user_deletion_execute,
    update_user_role_legacy,
)
from services import auth_service

_OTHER_ACTOR = {"id": "not-the-sole-admin", "name": "Someone Else", "role": "admin"}


def _sole_admin():
    return auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")


def test_cannot_demote_the_last_admin(brain):
    admin = _sole_admin()

    with pytest.raises(HTTPException) as exc:
        admin_update_user_role(admin["id"], UpdateRoleRequest(role="member"), _OTHER_ACTOR)
    assert exc.value.status_code == 409
    assert auth_service.get_user_by_id(admin["id"])["role"] == "admin"


def test_can_demote_an_admin_when_another_remains(brain):
    admin = _sole_admin()
    auth_service.create_user("other@example.com", "otherpass1", "Other Admin", role="admin")

    admin_update_user_role(admin["id"], UpdateRoleRequest(role="member"), _OTHER_ACTOR)

    assert auth_service.get_user_by_id(admin["id"])["role"] == "member"


def test_cannot_demote_the_last_admin_via_legacy_endpoint(brain):
    admin = _sole_admin()

    with pytest.raises(HTTPException) as exc:
        update_user_role_legacy(admin["id"], RoleUpdateRequest(role="member"), _OTHER_ACTOR)
    assert exc.value.status_code == 409
    assert auth_service.get_user_by_id(admin["id"])["role"] == "admin"


def test_cannot_delete_the_last_admin(brain):
    admin = _sole_admin()

    with pytest.raises(HTTPException) as exc:
        admin_delete_user(admin["id"], _OTHER_ACTOR)
    assert exc.value.status_code == 409
    assert auth_service.get_user_by_id(admin["id"]) is not None


def test_can_delete_an_admin_when_another_remains(brain):
    admin = _sole_admin()
    other_admin = auth_service.create_user(
        "other@example.com", "otherpass1", "Other Admin", role="admin"
    )

    admin_delete_user(other_admin["id"], _OTHER_ACTOR)

    assert auth_service.get_user_by_id(other_admin["id"]) is None
    assert auth_service.get_user_by_id(admin["id"]) is not None


def test_cannot_delete_the_last_admin_via_deletion_execute(brain):
    """The plain admin_delete_user() 409s away from this path (used when the
    target owns items already shared with someone), but execute() ultimately
    calls the same auth_service.delete_user() — a second real path that must
    carry the identical guard, not just the plain-delete one."""
    admin = _sole_admin()

    with pytest.raises(HTTPException) as exc:
        admin_user_deletion_execute(admin["id"], DeletionExecuteRequest(decisions=[]), _OTHER_ACTOR)
    assert exc.value.status_code == 409
    assert auth_service.get_user_by_id(admin["id"]) is not None


def test_demoting_a_non_admin_is_unaffected_by_the_guard(brain):
    _sole_admin()
    member = auth_service.create_user("member@example.com", "memberpass1", "Member", role="member")

    result = admin_update_user_role(member["id"], UpdateRoleRequest(role="admin"), _OTHER_ACTOR)

    assert result["role"] == "admin"
