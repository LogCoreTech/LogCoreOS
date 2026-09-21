"""Tests for the login-time 2FA gate — the critical seam identified during
planning: login_attempt() succeeding must NOT mint a full session when
totp_enabled is set; it must return a short-lived pending token instead,
consumed only by /2fa/verify-login. Endpoints called directly, bypassing
Depends(...), matching this suite's established convention."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pyotp
import pytest
from fastapi import HTTPException, Response

from routers.auth import (
    EnableTotpRequest,
    LoginRequest,
    VerifyLoginRequest,
    enable_totp,
    get_token,
    login,
    setup_totp,
    verify_login,
)
from services import auth_service, totp_service


@pytest.fixture(autouse=True)
def reset_lockout():
    yield
    auth_service._failed_logins.clear()


@pytest.fixture()
def user(brain):
    return auth_service.create_user("totp@example.com", "password123", "TOTP User")


def _fresh(user):
    return auth_service.get_user_by_id(user["id"])


def _enroll(user) -> list[str]:
    """Enrolls `user` in 2FA, returns their recovery codes."""
    setup_totp(user)
    secret = totp_service.decrypt_secret(_fresh(user)["totp_secret"])
    code = pyotp.TOTP(secret).now()
    return enable_totp(EnableTotpRequest(code=code), _fresh(user))["recovery_codes"]


def _current_code(user) -> str:
    secret = totp_service.decrypt_secret(_fresh(user)["totp_secret"])
    return pyotp.TOTP(secret).now()


def test_login_unaffected_when_totp_not_enabled(user):
    """Regression guard — the whole point of gating on totp_enabled."""
    response = Response()

    result = login(LoginRequest(email="totp@example.com", password="password123"), response)

    assert "totp_required" not in result
    assert result["id"] == user["id"]
    assert any(h[0] == b"set-cookie" for h in response.raw_headers)


def test_login_returns_pending_token_when_totp_enabled(user):
    _enroll(user)
    response = Response()

    result = login(LoginRequest(email="totp@example.com", password="password123"), response)

    assert result["totp_required"] is True
    assert "pending_token" in result
    assert not any(h[0] == b"set-cookie" for h in response.raw_headers)


def test_token_endpoint_returns_pending_token_when_totp_enabled(user):
    _enroll(user)

    result = get_token(LoginRequest(email="totp@example.com", password="password123"))

    assert result["totp_required"] is True
    assert "pending_token" in result


def test_verify_login_with_correct_code_mints_a_real_session(user):
    _enroll(user)
    login_result = login(LoginRequest(email="totp@example.com", password="password123"), Response())
    pending_token = login_result["pending_token"]

    response = Response()
    result = verify_login(
        VerifyLoginRequest(pending_token=pending_token, code=_current_code(user)), response
    )

    assert result["id"] == user["id"]
    assert any(h[0] == b"set-cookie" for h in response.raw_headers)


def test_verify_login_bearer_mode_returns_a_token_not_a_cookie(user):
    _enroll(user)
    token_result = get_token(LoginRequest(email="totp@example.com", password="password123"))

    response = Response()
    result = verify_login(
        VerifyLoginRequest(pending_token=token_result["pending_token"], code=_current_code(user)),
        response,
    )

    assert "token" in result
    assert not any(h[0] == b"set-cookie" for h in response.raw_headers)


def test_verify_login_with_recovery_code_succeeds_and_consumes_it(user):
    codes = _enroll(user)
    login_result = login(LoginRequest(email="totp@example.com", password="password123"), Response())

    result = verify_login(
        VerifyLoginRequest(pending_token=login_result["pending_token"], code=codes[0]), Response()
    )
    assert result["id"] == user["id"]
    assert len(_fresh(user)["totp_recovery_codes"]) == 9

    # The same code doesn't work twice.
    login_result2 = login(
        LoginRequest(email="totp@example.com", password="password123"), Response()
    )
    with pytest.raises(HTTPException) as exc:
        verify_login(
            VerifyLoginRequest(pending_token=login_result2["pending_token"], code=codes[0]),
            Response(),
        )
    assert exc.value.status_code == 401


def test_verify_login_with_wrong_code_rejected(user):
    _enroll(user)
    login_result = login(LoginRequest(email="totp@example.com", password="password123"), Response())

    with pytest.raises(HTTPException) as exc:
        verify_login(
            VerifyLoginRequest(pending_token=login_result["pending_token"], code="000000"),
            Response(),
        )
    assert exc.value.status_code == 401


def test_verify_login_rejects_a_tampered_or_wrong_purpose_token(user):
    _enroll(user)
    real_token = auth_service.create_token(_fresh(user))  # a real session JWT, purpose-less

    with pytest.raises(HTTPException) as exc:
        verify_login(
            VerifyLoginRequest(pending_token=real_token, code=_current_code(user)), Response()
        )
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        verify_login(
            VerifyLoginRequest(pending_token="not-a-real-token", code=_current_code(user)),
            Response(),
        )
    assert exc.value.status_code == 401


def test_verify_login_rejects_an_expired_pending_token(user, monkeypatch):
    _enroll(user)
    monkeypatch.setattr(totp_service, "_PENDING_TOKEN_MINUTES", -1)
    login_result = login(LoginRequest(email="totp@example.com", password="password123"), Response())

    with pytest.raises(HTTPException) as exc:
        verify_login(
            VerifyLoginRequest(
                pending_token=login_result["pending_token"], code=_current_code(user)
            ),
            Response(),
        )
    assert exc.value.status_code == 401
