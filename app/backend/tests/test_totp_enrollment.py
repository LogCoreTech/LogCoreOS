"""Tests for TOTP enrollment: setup -> enable -> disable, and the
recovery-codes regenerate flow. Endpoint functions called directly,
bypassing Depends(...), matching this suite's established convention (see
test_admin_last_admin_lockout.py). Each call re-fetches the user dict from
disk via `_fresh()` before passing it as `current_user` — auth_service's
own read-modify-write (`_load_auth()` re-reads the file fresh every call)
means a stale in-memory dict from an earlier fixture/call never reflects a
mutation another function just made."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pyotp
import pytest
from fastapi import HTTPException

from routers.auth import (
    DisableTotpRequest,
    EnableTotpRequest,
    RegenerateRecoveryCodesRequest,
    disable_totp,
    enable_totp,
    regenerate_recovery_codes,
    setup_totp,
    totp_status,
)
from services import auth_service, totp_service


@pytest.fixture()
def user(brain):
    return auth_service.create_user("totp@example.com", "password123", "TOTP User")


def _fresh(user):
    return auth_service.get_user_by_id(user["id"])


def _code_for(user):
    secret = totp_service.decrypt_secret(_fresh(user)["totp_secret"])
    return pyotp.TOTP(secret).now()


def test_status_before_setup(user):
    assert totp_status(user) == {"enabled": False, "recovery_codes_remaining": 0}


def test_setup_persists_a_pending_secret(user):
    result = setup_totp(user)

    assert "secret" in result
    assert result["otpauth_uri"].startswith("otpauth://totp/")
    assert result["qr_code"].startswith("data:image/png;base64,")
    stored = _fresh(user)
    assert stored.get("totp_secret")
    assert not stored.get("totp_enabled")


def test_enable_with_correct_code_succeeds(user):
    setup_totp(user)
    code = _code_for(user)

    result = enable_totp(EnableTotpRequest(code=code), _fresh(user))

    assert result["ok"] is True
    assert len(result["recovery_codes"]) == 10
    stored = _fresh(user)
    assert stored["totp_enabled"] is True
    assert len(stored["totp_recovery_codes"]) == 10


def test_enable_with_wrong_code_rejected(user):
    setup_totp(user)

    with pytest.raises(HTTPException) as exc:
        enable_totp(EnableTotpRequest(code="000000"), _fresh(user))
    assert exc.value.status_code == 400
    assert not _fresh(user).get("totp_enabled")


def test_enable_without_setup_rejected(user):
    with pytest.raises(HTTPException) as exc:
        enable_totp(EnableTotpRequest(code="123456"), user)
    assert exc.value.status_code == 400


def test_setup_refused_when_already_enabled(user):
    setup_totp(user)
    enable_totp(EnableTotpRequest(code=_code_for(user)), _fresh(user))

    with pytest.raises(HTTPException) as exc:
        setup_totp(_fresh(user))
    assert exc.value.status_code == 400


def test_disable_requires_correct_password_and_code(user):
    setup_totp(user)
    enable_totp(EnableTotpRequest(code=_code_for(user)), _fresh(user))

    with pytest.raises(HTTPException) as exc:
        disable_totp(
            DisableTotpRequest(current_password="wrong", code=_code_for(user)), _fresh(user)
        )
    assert exc.value.status_code == 400
    assert _fresh(user)["totp_enabled"] is True

    with pytest.raises(HTTPException) as exc:
        disable_totp(
            DisableTotpRequest(current_password="password123", code="000000"), _fresh(user)
        )
    assert exc.value.status_code == 400
    assert _fresh(user)["totp_enabled"] is True

    result = disable_totp(
        DisableTotpRequest(current_password="password123", code=_code_for(user)), _fresh(user)
    )

    assert result["ok"] is True
    stored = _fresh(user)
    assert stored["totp_enabled"] is False
    assert stored["totp_secret"] is None
    assert stored["totp_recovery_codes"] == []


def test_disable_accepts_a_recovery_code_instead_of_a_totp_code(user):
    setup_totp(user)
    codes = enable_totp(EnableTotpRequest(code=_code_for(user)), _fresh(user))["recovery_codes"]

    result = disable_totp(
        DisableTotpRequest(current_password="password123", code=codes[0]), _fresh(user)
    )

    assert result["ok"] is True


def test_regenerate_recovery_codes_invalidates_the_old_set(user):
    setup_totp(user)
    original = enable_totp(EnableTotpRequest(code=_code_for(user)), _fresh(user))["recovery_codes"]

    result = regenerate_recovery_codes(
        RegenerateRecoveryCodesRequest(code=_code_for(user)), _fresh(user)
    )

    assert len(result["recovery_codes"]) == 10
    assert set(result["recovery_codes"]).isdisjoint(original)
    # The old codes no longer work.
    with pytest.raises(HTTPException):
        disable_totp(
            DisableTotpRequest(current_password="password123", code=original[0]), _fresh(user)
        )
