"""GET /me's new must_setup_2fa/totp_enabled fields — a nag, deliberately
mirroring must_change_password's confirmed client-side-only enforcement
style (this is "please go set this up," not a security boundary)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pyotp
import pytest

from routers.auth import (
    AdminSettingsRequest,
    EnableTotpRequest,
    enable_totp,
    me,
    setup_totp,
    update_admin_settings,
)
from services import auth_service, totp_service


def _fresh(user):
    return auth_service.get_user_by_id(user["id"])


def _enroll(user):
    setup_totp(user)
    secret = totp_service.decrypt_secret(_fresh(user)["totp_secret"])
    code = pyotp.TOTP(secret).now()
    enable_totp(EnableTotpRequest(code=code), _fresh(user))


def test_must_setup_2fa_false_when_policy_off(brain):
    member = auth_service.create_user("member@example.com", "password123", "Member")
    assert me(member)["must_setup_2fa"] is False


def test_must_setup_2fa_true_for_member_when_policy_is_all(brain):
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    _enroll(admin)
    update_admin_settings(AdminSettingsRequest(require_2fa="all"), _fresh(admin))
    member = auth_service.create_user("member@example.com", "password123", "Member")

    assert me(member)["must_setup_2fa"] is True
    assert me(member)["totp_enabled"] is False


def test_must_setup_2fa_false_for_member_when_policy_is_admin_only(brain):
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    _enroll(admin)
    update_admin_settings(AdminSettingsRequest(require_2fa="admin"), _fresh(admin))
    member = auth_service.create_user("member@example.com", "password123", "Member")

    assert me(member)["must_setup_2fa"] is False
    assert me(_fresh(admin))["must_setup_2fa"] is False  # admin already has it enabled


def test_must_setup_2fa_clears_once_enrolled(brain):
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    _enroll(admin)
    update_admin_settings(AdminSettingsRequest(require_2fa="all"), _fresh(admin))
    member = auth_service.create_user("member@example.com", "password123", "Member")
    assert me(member)["must_setup_2fa"] is True

    _enroll(member)

    assert me(_fresh(member))["must_setup_2fa"] is False
    assert me(_fresh(member))["totp_enabled"] is True
