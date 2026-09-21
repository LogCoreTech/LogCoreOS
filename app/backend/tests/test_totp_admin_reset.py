"""Tests for POST /admin/users/{user_id}/2fa/reset — mirrors
admin_reset_password's own test conventions. No admin_count() guard is
expected here (disabling someone's 2FA never touches admin-privilege
scarcity the way demoting/deleting an admin does)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pyotp
import pytest
from fastapi import HTTPException

from routers.auth import EnableTotpRequest, admin_reset_totp, enable_totp, setup_totp
from services import audit_log, auth_service, totp_service

_ADMIN = {"id": "admin-id", "name": "Admin", "role": "admin"}


@pytest.fixture()
def enrolled_user(brain):
    user = auth_service.create_user("member@example.com", "password123", "Member")
    setup_totp(user)
    fresh = auth_service.get_user_by_id(user["id"])
    secret = totp_service.decrypt_secret(fresh["totp_secret"])
    code = pyotp.TOTP(secret).now()
    enable_totp(EnableTotpRequest(code=code), fresh)
    return user


def test_admin_reset_clears_all_totp_fields(enrolled_user):
    result = admin_reset_totp(enrolled_user["id"], _ADMIN)

    assert result == {"ok": True}
    stored = auth_service.get_user_by_id(enrolled_user["id"])
    assert stored["totp_enabled"] is False
    assert stored["totp_secret"] is None
    assert stored["totp_recovery_codes"] == []


def test_admin_reset_writes_an_audit_log_entry(enrolled_user):
    admin_reset_totp(enrolled_user["id"], _ADMIN)

    entries = audit_log.list_entries(10)
    entry = next(e for e in entries if e["action"] == "user.2fa_admin_reset")
    assert entry["target"] == "Member"
    assert entry["actor"]["name"] == "Admin"


def test_admin_reset_404s_for_unknown_user(brain):
    with pytest.raises(HTTPException) as exc:
        admin_reset_totp("no-such-user", _ADMIN)
    assert exc.value.status_code == 404


def test_admin_reset_is_a_noop_on_a_user_without_2fa(brain):
    user = auth_service.create_user("plain@example.com", "password123", "Plain User")

    result = admin_reset_totp(user["id"], _ADMIN)

    assert result == {"ok": True}
