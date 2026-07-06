"""Tests for services/suggestions_service.py."""

import sys
from datetime import date
from unittest.mock import MagicMock

import pytest

# Stub auth_service to avoid broken jose/cryptography import in CI environment
_mock_auth = MagicMock()
_mock_auth.get_user_by_name.return_value = None
_mock_auth.today_for_user.return_value = date.today()
sys.modules.setdefault("services.auth_service", _mock_auth)

import services.suggestions_service as svc

USER = "TestUser"


@pytest.fixture()
def user_dir(brain):
    """Ensure the user directory exists."""
    d = brain / "USERS" / USER
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


def test_get_config_returns_defaults(user_dir):
    cfg = svc.get_config(USER)
    assert "daily_digest" in cfg
    assert "overdue_alert" in cfg
    assert "weekly_review" in cfg
    assert "goal_drift" in cfg
    assert cfg["daily_digest"]["enabled"] is True
    assert cfg["custom"] == []


# ---------------------------------------------------------------------------
# update_config
# ---------------------------------------------------------------------------


def test_update_builtin_config(user_dir):
    svc.update_config(USER, "daily_digest", {"enabled": False})
    cfg = svc.get_config(USER)
    assert cfg["daily_digest"]["enabled"] is False


def test_update_builtin_config_partial(user_dir):
    svc.update_config(USER, "goal_drift", {"days_threshold": 7})
    cfg = svc.get_config(USER)
    assert cfg["goal_drift"]["days_threshold"] == 7
    assert cfg["goal_drift"]["enabled"] is True  # unchanged


def test_update_unknown_builtin_does_not_raise(user_dir):
    result = svc.update_config(USER, "nonexistent", {"enabled": False})
    assert "custom" in result


# ---------------------------------------------------------------------------
# create_custom / delete_custom
# ---------------------------------------------------------------------------


def test_create_custom(user_dir):
    custom = svc.create_custom(
        USER,
        {"name": "Check Goals", "prompt": "Review my goals.", "hour": 9, "delivery": ["in_app"]},
    )
    assert custom["name"] == "Check Goals"
    assert "id" in custom
    cfg = svc.get_config(USER)
    assert any(c["id"] == custom["id"] for c in cfg["custom"])


def test_delete_custom_success(user_dir):
    custom = svc.create_custom(
        USER,
        {"name": "Temp", "prompt": "temp prompt", "hour": 8, "delivery": ["in_app"]},
    )
    assert svc.delete_custom(USER, custom["id"]) is True
    cfg = svc.get_config(USER)
    assert not any(c["id"] == custom["id"] for c in cfg["custom"])


def test_delete_custom_not_found(user_dir):
    assert svc.delete_custom(USER, "00000000-0000-0000-0000-000000000000") is False


# ---------------------------------------------------------------------------
# Notification inbox
# ---------------------------------------------------------------------------


def test_add_and_get_notification(user_dir):
    svc.add_notification(USER, "Title", "Body", "test_source", "in_app")
    notifs = svc.get_notifications(USER)
    assert len(notifs) == 1
    assert notifs[0]["title"] == "Title"
    assert notifs[0]["read"] is False


def test_get_notifications_limit(user_dir):
    for i in range(5):
        svc.add_notification(USER, f"N{i}", "body", "src", "in_app")
    notifs = svc.get_notifications(USER, limit=3)
    assert len(notifs) == 3


def test_get_notifications_filter_by_delivery(user_dir):
    svc.add_notification(USER, "Push notif", "body", "src", "push")
    svc.add_notification(USER, "In-app notif", "body", "src", "in_app")
    in_app = svc.get_notifications(USER, delivery="in_app")
    assert all(n["delivery"] == "in_app" for n in in_app)
    assert len(in_app) >= 1


def test_mark_read(user_dir):
    notif = svc.add_notification(USER, "Title", "Body", "src", "in_app")
    assert svc.mark_read(USER, notif["id"]) is True
    notifs = svc.get_notifications(USER)
    assert notifs[0]["read"] is True


def test_mark_read_not_found(user_dir):
    assert svc.mark_read(USER, "bad-id") is False


def test_clear_notifications(user_dir):
    svc.add_notification(USER, "A", "b", "src", "in_app")
    svc.add_notification(USER, "C", "d", "src", "in_app")
    svc.clear_notifications(USER)
    notifs = svc.get_notifications(USER)
    assert all(n["read"] is True for n in notifs)


def test_notification_cap(user_dir):
    for i in range(55):
        svc.add_notification(USER, f"N{i}", "body", "src", "in_app")
    notifs = svc.get_notifications(USER, limit=200)
    assert len(notifs) <= svc._NOTIF_CAP
