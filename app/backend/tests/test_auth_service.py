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
    # Clear in-memory revocation set + login-lockout state between tests
    auth_service._revoked_jtis.clear()
    auth_service._failed_logins.clear()


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


# --- Account-scoped login lockout -------------------------------------------


def test_login_attempt_success(brain):
    auth_service.create_user("lock@example.com", "rightpass", "Lock User")
    user, remaining = auth_service.login_attempt("lock@example.com", "rightpass")
    assert remaining == 0
    assert user is not None and user["email"] == "lock@example.com"


def test_login_attempt_bad_password_records_failure(brain):
    auth_service.create_user("lock@example.com", "rightpass", "Lock User")
    user, remaining = auth_service.login_attempt("lock@example.com", "nope")
    assert user is None and remaining == 0
    assert len(auth_service._failed_logins["lock@example.com"]) == 1


def test_account_locks_after_threshold(brain):
    auth_service.create_user("lock@example.com", "rightpass", "Lock User")
    for _ in range(auth_service._LOCKOUT_THRESHOLD):
        user, remaining = auth_service.login_attempt("lock@example.com", "wrong")
        assert user is None
    # Next attempt is refused with a positive cooldown, even with the RIGHT password
    user, remaining = auth_service.login_attempt("lock@example.com", "rightpass")
    assert user is None
    assert remaining > 0


def test_lockout_is_case_insensitive_on_email(brain):
    auth_service.create_user("lock@example.com", "rightpass", "Lock User")
    for _ in range(auth_service._LOCKOUT_THRESHOLD):
        auth_service.login_attempt("LOCK@EXAMPLE.COM", "wrong")
    assert auth_service.account_lock_remaining("lock@example.com") > 0


def test_successful_login_clears_failure_counter(brain):
    auth_service.create_user("lock@example.com", "rightpass", "Lock User")
    for _ in range(auth_service._LOCKOUT_THRESHOLD - 1):
        auth_service.login_attempt("lock@example.com", "wrong")
    # One short of the threshold, a success resets the counter to empty
    user, remaining = auth_service.login_attempt("lock@example.com", "rightpass")
    assert user is not None and remaining == 0
    assert "lock@example.com" not in auth_service._failed_logins


def test_lock_remaining_zero_when_no_failures(brain):
    assert auth_service.account_lock_remaining("nobody@example.com") == 0


# ---------------------------------------------------------------------------
# update_user_role / delete_user — race-safety (fixed 2026-09-07)
# ---------------------------------------------------------------------------


def test_update_user_role_holds_the_lock_no_lost_updates(brain, monkeypatch):
    """The actual bug: update_user_role()/delete_user() were the only two writers
    of auth.json with no lock, unlike every sibling function in this file. Mirrors
    test_file_service.py's own test_update_json_serializes_concurrent_writers_no_lost_update
    for the identical bug class — a widened read-to-write window via a slowed
    _save_auth, N concurrent writers each touching a DIFFERENT user's role in the
    same shared file, and an assertion that none of the N changes got silently
    reverted by another writer's stale full-file overwrite."""
    import threading
    import time

    real_save = auth_service._save_auth

    def slow_save(data):
        time.sleep(0.01)
        real_save(data)

    monkeypatch.setattr(auth_service, "_save_auth", slow_save)

    users = [auth_service.create_user(f"user{i}@example.com", "password1", f"User{i}") for i in range(20)]

    threads = [
        threading.Thread(target=auth_service.update_user_role, args=(u["id"], "admin")) for u in users
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    reloaded = {u["id"]: u["role"] for u in auth_service._load_auth()["users"]}
    assert all(reloaded[u["id"]] == "admin" for u in users)


def test_delete_user_holds_the_lock_no_lost_deletes(brain, monkeypatch):
    """Same bug class as above, for delete_user(): N concurrent deletes of N
    different users must all land, not silently un-delete each other via a
    stale full-file overwrite."""
    import threading
    import time

    real_save = auth_service._save_auth

    def slow_save(data):
        time.sleep(0.01)
        real_save(data)

    monkeypatch.setattr(auth_service, "_save_auth", slow_save)

    users = [auth_service.create_user(f"user{i}@example.com", "password1", f"User{i}") for i in range(20)]

    threads = [threading.Thread(target=auth_service.delete_user, args=(u["id"],)) for u in users]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert auth_service._load_auth()["users"] == []
