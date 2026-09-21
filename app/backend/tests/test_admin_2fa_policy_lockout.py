"""Regression coverage for the "require 2FA" policy self-lockout guard —
mirrors test_admin_last_admin_lockout.py's own structure exactly: an admin
must not be able to turn on a policy that would immediately lock THEM out
(they need their own 2FA enrolled first). Different check than the last-
admin guard (not admin-scarcity — "don't let the person flipping the switch
lock themselves out"), same 409 style."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pyotp
import pytest
from fastapi import HTTPException

from routers.auth import (
    AdminSettingsRequest,
    EnableTotpRequest,
    enable_totp,
    setup_totp,
    update_admin_settings,
)
from services import auth_service, totp_service


@pytest.fixture()
def admin(brain):
    return auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")


def _fresh(user):
    return auth_service.get_user_by_id(user["id"])


def _enroll(user):
    setup_totp(user)
    secret = totp_service.decrypt_secret(_fresh(user)["totp_secret"])
    code = pyotp.TOTP(secret).now()
    enable_totp(EnableTotpRequest(code=code), _fresh(user))


def test_cannot_require_2fa_without_own_totp_enabled(admin):
    with pytest.raises(HTTPException) as exc:
        update_admin_settings(AdminSettingsRequest(require_2fa="admin"), admin)
    assert exc.value.status_code == 409
    assert auth_service.get_system_settings().get("require_2fa", "off") == "off"


def test_cannot_require_2fa_for_all_without_own_totp_enabled(admin):
    with pytest.raises(HTTPException) as exc:
        update_admin_settings(AdminSettingsRequest(require_2fa="all"), admin)
    assert exc.value.status_code == 409


def test_can_require_2fa_once_own_totp_is_enabled(admin):
    _enroll(admin)

    result = update_admin_settings(AdminSettingsRequest(require_2fa="admin"), _fresh(admin))

    assert result["require_2fa"] == "admin"
    assert auth_service.get_system_settings()["require_2fa"] == "admin"


def test_turning_the_policy_back_off_is_never_blocked(admin):
    _enroll(admin)
    update_admin_settings(AdminSettingsRequest(require_2fa="all"), _fresh(admin))

    result = update_admin_settings(AdminSettingsRequest(require_2fa="off"), admin)

    assert result["require_2fa"] == "off"


def test_unrelated_settings_updates_are_unaffected_by_the_guard(admin):
    result = update_admin_settings(AdminSettingsRequest(session_minutes=120), admin)
    assert result["session_minutes"] == 120
