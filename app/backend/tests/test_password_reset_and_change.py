"""Coverage for the admin password-reset flow and the self-service
change-password endpoint it depends on (2026-09-18, TASKS.md backlog item:
"Admin: reset a user's password — generates a random temp password; user
must set their own on next login. No UI reveal, no in-app notification
needed"). One endpoint (POST /me/password) serves both the forced-reset
case AND the general "change my known password" case that was itself a
separate, longstanding backlog gap — the temp password from a reset IS the
user's current_password the first time they call it."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException

from routers.auth import ChangePasswordRequest, admin_reset_password, change_password, me
from services import auth_service


def test_admin_reset_password_sets_must_change_flag_and_returns_temp_password(brain):
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")

    result = admin_reset_password(bob["id"], admin)

    assert "temp_password" in result and len(result["temp_password"]) > 10
    updated = auth_service.get_user_by_id(bob["id"])
    assert updated["must_change_password"] is True
    assert auth_service.verify_password(result["temp_password"], updated["hashed_password"])
    # The old password no longer works.
    assert not auth_service.verify_password("bobpass1", updated["hashed_password"])


def test_me_reflects_must_change_password(brain):
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")
    assert me(bob)["must_change_password"] is False

    auth_service.update_user(bob["id"], {"must_change_password": True})
    bob = auth_service.get_user_by_id(bob["id"])
    assert me(bob)["must_change_password"] is True


def test_change_password_with_the_temp_password_clears_the_flag(brain):
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")
    reset = admin_reset_password(bob["id"], admin)
    bob = auth_service.get_user_by_id(bob["id"])  # refresh — now holds the temp password

    change_password(
        ChangePasswordRequest(current_password=reset["temp_password"], new_password="newpass123"),
        bob,
    )

    updated = auth_service.get_user_by_id(bob["id"])
    assert updated["must_change_password"] is False
    assert auth_service.verify_password("newpass123", updated["hashed_password"])


def test_change_password_rejects_wrong_current_password(brain):
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")

    with pytest.raises(HTTPException) as exc:
        change_password(
            ChangePasswordRequest(current_password="wrongpass", new_password="newpass123"), bob
        )
    assert exc.value.status_code == 400
    # Nothing changed.
    updated = auth_service.get_user_by_id(bob["id"])
    assert auth_service.verify_password("bobpass1", updated["hashed_password"])


def test_change_password_enforces_min_length():
    with pytest.raises(Exception):  # pydantic ValidationError
        ChangePasswordRequest(current_password="whatever", new_password="short")


def test_admin_reset_password_on_unknown_user_404s(brain):
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")

    with pytest.raises(HTTPException) as exc:
        admin_reset_password("no-such-id", admin)
    assert exc.value.status_code == 404
