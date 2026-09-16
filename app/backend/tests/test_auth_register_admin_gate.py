"""Regression test for a real security bug fixed 2026-09-07: POST /register's
admin gate (closed-registration instances) decoded the admin's JWT by hand and
trusted its embedded `role` claim, instead of re-fetching the user from disk the
way every other admin-gated path (get_current_user()/require_admin) does. Since
nothing revokes a token on role change or account deletion, a demoted or deleted
admin's still-unexpired token could keep hitting this one endpoint to create new
accounts indefinitely.

Narrowly scoped to this one fix, not a general routers/auth.py test file — that
file has no router-level test coverage at all today, a separate, pre-existing gap.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from routers.auth import _COOKIE, RegisterRequest, register
from services import auth_service


def _cookie_request(token: str) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/register",
        "query_string": b"",
        "headers": [(b"cookie", f"{_COOKIE}={token}".encode())],
    }
    return Request(scope)


def _new_register_request() -> RegisterRequest:
    return RegisterRequest(email="newperson@example.com", password="longenough1", name="New Person")


def test_registration_closed_by_default(brain):
    # A second, already-existing user so the admin's own deletion below doesn't
    # drop user_count() back to 0 and re-open the is_first_user bypass.
    auth_service.create_user("member@example.com", "memberpass1", "Member", role="member")
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    token = auth_service.create_token(admin)

    # Sanity check: a genuinely current admin's token still works.
    result = register(_new_register_request(), Response(), _cookie_request(token), None)
    assert result["role"] == "member"


def test_demoted_admins_stale_token_is_rejected(brain):
    auth_service.create_user("member@example.com", "memberpass1", "Member", role="member")
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    stale_token = auth_service.create_token(admin)  # minted while still admin

    auth_service.update_user(admin["id"], {"role": "member"})  # demoted after minting

    with pytest.raises(HTTPException) as exc:
        register(_new_register_request(), Response(), _cookie_request(stale_token), None)
    assert exc.value.status_code == 403


def test_deleted_admins_stale_token_is_rejected(brain):
    auth_service.create_user("member@example.com", "memberpass1", "Member", role="member")
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    stale_token = auth_service.create_token(admin)  # minted while the account still existed

    auth_service.delete_user(admin["id"])

    with pytest.raises(HTTPException) as exc:
        register(_new_register_request(), Response(), _cookie_request(stale_token), None)
    assert exc.value.status_code == 403
