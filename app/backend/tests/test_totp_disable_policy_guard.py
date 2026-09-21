"""Regression coverage for a real gap found after shipping app-level 2FA:
disable_totp() originally had no idea the admin "require_2fa" policy existed
at all, so a user whose 2FA was mandatory (policy "admin" or "all") could
still self-disable it via the normal Settings -> Security flow, with no
server-side block — "mandatory" was only ever a client-side nag to enroll
(must_setup_2fa on /me), never actually enforced once enrolled. Fixed by
having disable_totp() consult totp_service.policy_requires_2fa_for() before
even checking the password/code, mirroring the shape of every other guard
in this router (check first, fail loud, before touching anything secret)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pyotp
import pytest
from fastapi import HTTPException

from routers.auth import (
    AdminSettingsRequest,
    DisableTotpRequest,
    EnableTotpRequest,
    disable_totp,
    enable_totp,
    setup_totp,
    update_admin_settings,
)
from services import auth_service, totp_service


@pytest.fixture()
def admin(brain):
    return auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")


@pytest.fixture()
def member(brain):
    return auth_service.create_user("member@example.com", "memberpass1", "Member")


def _fresh(user):
    return auth_service.get_user_by_id(user["id"])


def _enroll(user):
    setup_totp(user)
    secret = totp_service.decrypt_secret(_fresh(user)["totp_secret"])
    code = pyotp.TOTP(secret).now()
    enable_totp(EnableTotpRequest(code=code), _fresh(user))


def _code_for(user):
    secret = totp_service.decrypt_secret(_fresh(user)["totp_secret"])
    return pyotp.TOTP(secret).now()


def test_admin_cannot_disable_own_2fa_when_policy_is_admin(admin):
    _enroll(admin)
    update_admin_settings(AdminSettingsRequest(require_2fa="admin"), _fresh(admin))

    with pytest.raises(HTTPException) as exc:
        disable_totp(
            DisableTotpRequest(current_password="adminpass1", code=_code_for(admin)),
            _fresh(admin),
        )
    assert exc.value.status_code == 403
    assert _fresh(admin)["totp_enabled"] is True


def test_member_cannot_disable_own_2fa_when_policy_is_all(admin, member):
    _enroll(admin)
    update_admin_settings(AdminSettingsRequest(require_2fa="all"), _fresh(admin))
    _enroll(member)

    with pytest.raises(HTTPException) as exc:
        disable_totp(
            DisableTotpRequest(current_password="memberpass1", code=_code_for(member)),
            _fresh(member),
        )
    assert exc.value.status_code == 403
    assert _fresh(member)["totp_enabled"] is True


def test_member_can_still_disable_when_policy_is_admin_only(admin, member):
    _enroll(admin)
    update_admin_settings(AdminSettingsRequest(require_2fa="admin"), _fresh(admin))
    _enroll(member)

    result = disable_totp(
        DisableTotpRequest(current_password="memberpass1", code=_code_for(member)),
        _fresh(member),
    )

    assert result["ok"] is True
    assert _fresh(member)["totp_enabled"] is False


def test_disable_still_works_once_policy_is_turned_back_off(admin):
    _enroll(admin)
    update_admin_settings(AdminSettingsRequest(require_2fa="all"), _fresh(admin))
    update_admin_settings(AdminSettingsRequest(require_2fa="off"), _fresh(admin))

    result = disable_totp(
        DisableTotpRequest(current_password="adminpass1", code=_code_for(admin)),
        _fresh(admin),
    )

    assert result["ok"] is True
