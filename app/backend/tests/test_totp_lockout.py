"""Wrong TOTP codes must trip the SAME account-lockout counter as wrong
passwords — one unified lockout surface (verify_second_factor() is a
structural mirror of auth_service.login_attempt(), keyed by the same
lowercased email), not a second, parallel counter. Mirrors
test_auth_service.py's own lockout tests exactly, just interleaving
password and TOTP failures."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pyotp
import pytest

from routers.auth import EnableTotpRequest, enable_totp, setup_totp
from services import auth_service, totp_service

EMAIL = "totp@example.com"


@pytest.fixture(autouse=True)
def reset_lockout():
    yield
    auth_service._failed_logins.clear()


@pytest.fixture()
def user(brain):
    return auth_service.create_user(EMAIL, "password123", "TOTP User")


def _fresh(user):
    return auth_service.get_user_by_id(user["id"])


def _enroll(user):
    setup_totp(user)
    secret = totp_service.decrypt_secret(_fresh(user)["totp_secret"])
    code = pyotp.TOTP(secret).now()
    enable_totp(EnableTotpRequest(code=code), _fresh(user))


def test_wrong_totp_codes_alone_trip_the_lockout(user):
    _enroll(user)
    for _ in range(auth_service._LOCKOUT_THRESHOLD):
        ok, locked = totp_service.verify_second_factor(EMAIL, _fresh(user), "000000")
        assert ok is False

    assert auth_service.account_lock_remaining(EMAIL) > 0


def test_wrong_passwords_and_wrong_totp_codes_share_one_counter(user):
    _enroll(user)
    half = auth_service._LOCKOUT_THRESHOLD // 2
    for _ in range(half):
        auth_service.login_attempt(EMAIL, "wrongpassword")
    for _ in range(auth_service._LOCKOUT_THRESHOLD - half):
        totp_service.verify_second_factor(EMAIL, _fresh(user), "000000")

    assert auth_service.account_lock_remaining(EMAIL) > 0


def test_verify_second_factor_refuses_once_locked_even_with_the_right_code(user):
    _enroll(user)
    for _ in range(auth_service._LOCKOUT_THRESHOLD):
        auth_service.login_attempt(EMAIL, "wrongpassword")

    secret = totp_service.decrypt_secret(_fresh(user)["totp_secret"])
    real_code = pyotp.TOTP(secret).now()
    ok, locked = totp_service.verify_second_factor(EMAIL, _fresh(user), real_code)

    assert ok is False
    assert locked > 0


def test_successful_totp_verify_clears_the_failure_counter(user):
    _enroll(user)
    for _ in range(auth_service._LOCKOUT_THRESHOLD - 1):
        auth_service.login_attempt(EMAIL, "wrongpassword")

    secret = totp_service.decrypt_secret(_fresh(user)["totp_secret"])
    real_code = pyotp.TOTP(secret).now()
    ok, locked = totp_service.verify_second_factor(EMAIL, _fresh(user), real_code)

    assert ok is True and locked == 0
    assert EMAIL not in auth_service._failed_logins
