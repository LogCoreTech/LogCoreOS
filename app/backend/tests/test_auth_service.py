"""Tests for auth_service — user creation, authentication, token operations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import auth_service


@pytest.fixture(autouse=True)
def reset_auth(brain):
    """Each test gets a fresh brain directory with no users."""
    yield
    # Clear in-memory revocation set between tests
    auth_service._revoked_jtis.clear()


def test_create_and_retrieve_user(brain):
    user = auth_service.create_user("test@example.com", "password123", "Test User", role="admin")
    assert user["email"] == "test@example.com"
    assert user["name"] == "Test User"
    assert user["role"] == "admin"


def test_email_normalized_to_lowercase(brain):
    auth_service.create_user("USER@EXAMPLE.COM", "password123", "Alice")
    found = auth_service.get_user_by_email("user@example.com")
    assert found is not None
    assert found["email"] == "user@example.com"


def test_duplicate_email_raises(brain):
    auth_service.create_user("dupe@example.com", "password123", "First")
    with pytest.raises(ValueError, match="already registered"):
        auth_service.create_user("dupe@example.com", "password456", "Second")


def test_duplicate_email_case_insensitive(brain):
    auth_service.create_user("dupe@example.com", "password123", "First")
    with pytest.raises(ValueError, match="already registered"):
        auth_service.create_user("DUPE@EXAMPLE.COM", "password456", "Second")


def test_second_user_is_member(brain):
    auth_service.create_user("admin@example.com", "password123", "Admin", role="admin")
    member = auth_service.create_user("member@example.com", "password123", "Member")
    assert member["role"] == "member"


def test_invalid_name_raises(brain):
    with pytest.raises(ValueError):
        auth_service.create_user("x@example.com", "password123", "../../etc/passwd")


def test_authenticate_success(brain):
    auth_service.create_user("auth@example.com", "mypassword", "Auth User")
    user = auth_service.authenticate("auth@example.com", "mypassword")
    assert user is not None
    assert user["email"] == "auth@example.com"


def test_authenticate_wrong_password(brain):
    auth_service.create_user("auth@example.com", "mypassword", "Auth User")
    assert auth_service.authenticate("auth@example.com", "wrongpassword") is None


def test_authenticate_unknown_email(brain):
    assert auth_service.authenticate("nobody@example.com", "password") is None


def test_authenticate_unknown_email_still_runs_bcrypt(brain, monkeypatch):
    """Constant-time login: an unknown email must still trigger a bcrypt verify
    (against the dummy hash) so response timing can't be used to enumerate users."""
    calls: list[str] = []
    real_verify = auth_service.verify_password

    def _spy(plain, hashed):
        calls.append(hashed)
        return real_verify(plain, hashed)

    monkeypatch.setattr(auth_service, "verify_password", _spy)
    assert auth_service.authenticate("nobody@example.com", "password") is None
    assert calls == [auth_service._DUMMY_HASH]


def test_token_round_trip(brain):
    user = auth_service.create_user("tok@example.com", "password123", "Token User")
    token = auth_service.create_token(user)
    payload = auth_service.decode_token(token)
    assert payload is not None
    assert payload["sub"] == user["id"]


def test_revoked_token_rejected(brain):
    user = auth_service.create_user("rev@example.com", "password123", "Rev User")
    token = auth_service.create_token(user)
    payload = auth_service.decode_token(token)
    jti = payload["jti"]
    auth_service.revoke_token(jti)
    assert auth_service.decode_token(token) is None


def test_update_user(brain):
    user = auth_service.create_user("upd@example.com", "password123", "Update User")
    updated = auth_service.update_user(user["id"], {"timezone": "America/New_York"})
    assert updated["timezone"] == "America/New_York"
    refetched = auth_service.get_user_by_id(user["id"])
    assert refetched["timezone"] == "America/New_York"


def test_system_settings_persist(brain):
    auth_service.update_system_settings({"allow_open_registration": True})
    settings = auth_service.get_system_settings()
    assert settings["allow_open_registration"] is True
