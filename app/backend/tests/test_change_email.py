"""Coverage for the self-service email-change endpoint (2026-09-20,
Settings -> Account's "Update Email" popup — owner feedback the same day
2FA shipped: email/password should read as fixed facts with an
"Update Email"/"Reset Password" button each, not always-open fields).
Mirrors test_password_reset_and_change.py's own shape for the sibling
POST /me/password endpoint."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException

from routers.auth import ChangeEmailRequest, change_email, me
from services import auth_service


def test_change_email_updates_email_and_is_reflected_in_me(brain):
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")

    result = change_email(
        ChangeEmailRequest(current_password="bobpass1", new_email="bob-new@example.com"), bob
    )

    assert result == {"ok": True, "email": "bob-new@example.com"}
    updated = auth_service.get_user_by_id(bob["id"])
    assert updated["email"] == "bob-new@example.com"
    assert me(updated)["email"] == "bob-new@example.com"


def test_change_email_normalizes_to_lowercase(brain):
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")

    change_email(
        ChangeEmailRequest(current_password="bobpass1", new_email="Bob-New@Example.COM"), bob
    )

    updated = auth_service.get_user_by_id(bob["id"])
    assert updated["email"] == "bob-new@example.com"


def test_change_email_rejects_wrong_current_password(brain):
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")

    with pytest.raises(HTTPException) as exc:
        change_email(
            ChangeEmailRequest(current_password="wrongpass", new_email="bob-new@example.com"), bob
        )
    assert exc.value.status_code == 400
    updated = auth_service.get_user_by_id(bob["id"])
    assert updated["email"] == "bob@example.com"  # unchanged


def test_change_email_rejects_email_already_in_use(brain):
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")
    auth_service.create_user("alice@example.com", "alicepass1", "Alice", role="member")

    with pytest.raises(HTTPException) as exc:
        change_email(
            ChangeEmailRequest(current_password="bobpass1", new_email="alice@example.com"), bob
        )
    assert exc.value.status_code == 400
    updated = auth_service.get_user_by_id(bob["id"])
    assert updated["email"] == "bob@example.com"  # unchanged


def test_change_email_allows_keeping_own_current_email(brain):
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")

    result = change_email(
        ChangeEmailRequest(current_password="bobpass1", new_email="bob@example.com"), bob
    )

    assert result["email"] == "bob@example.com"


def test_change_email_rejects_invalid_email_format():
    with pytest.raises(Exception):  # pydantic ValidationError
        ChangeEmailRequest(current_password="whatever", new_email="not-an-email")
