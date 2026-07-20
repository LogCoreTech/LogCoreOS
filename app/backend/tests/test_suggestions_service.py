"""Tests for services/suggestions_service.py."""

import sys
from datetime import date, datetime, timedelta, timezone
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


# ---------------------------------------------------------------------------
# run_channel_rotation_reminders
# ---------------------------------------------------------------------------


def _iso(dt):
    return dt.isoformat()


def _stub_users(monkeypatch, users):
    """Wire svc.list_users/get_user_by_id/update_user to an in-memory user list."""
    by_id = {u["id"]: u for u in users}

    def _list_users():
        return [{"id": u["id"], "name": u["name"]} for u in users]

    def _get_user_by_id(uid):
        return by_id.get(uid)

    def _update_user(uid, updates):
        by_id[uid].update(updates)
        return by_id[uid]

    monkeypatch.setattr(svc, "list_users", _list_users)
    monkeypatch.setattr(svc, "get_user_by_id", _get_user_by_id)
    monkeypatch.setattr(svc, "update_user", _update_user)
    return by_id


def test_rotation_reminder_fires_when_stale(user_dir, monkeypatch):
    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=31)
    users = [{"id": "u1", "name": USER, "channel_rotated_at": _iso(stale)}]
    by_id = _stub_users(monkeypatch, users)
    sent = []
    monkeypatch.setattr(svc, "notify_user", lambda *a, **k: sent.append((a, k)))

    count = svc.run_channel_rotation_reminders(now=now)

    assert count == 1
    assert len(sent) == 1
    assert by_id["u1"]["channel_reminder_at"]  # dedup stamp written


def test_rotation_reminder_skips_recent_rotation(user_dir, monkeypatch):
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=5)
    users = [{"id": "u1", "name": USER, "channel_rotated_at": _iso(recent)}]
    _stub_users(monkeypatch, users)
    sent = []
    monkeypatch.setattr(svc, "notify_user", lambda *a, **k: sent.append((a, k)))

    assert svc.run_channel_rotation_reminders(now=now) == 0
    assert sent == []


def test_rotation_reminder_falls_back_to_created_at(user_dir, monkeypatch):
    """Users who have never rotated are measured from account creation."""
    now = datetime.now(timezone.utc)
    old_created = now - timedelta(days=45)
    users = [{"id": "u1", "name": USER, "created_at": _iso(old_created)}]
    _stub_users(monkeypatch, users)
    sent = []
    monkeypatch.setattr(svc, "notify_user", lambda *a, **k: sent.append((a, k)))

    assert svc.run_channel_rotation_reminders(now=now) == 1
    assert len(sent) == 1


def test_rotation_reminder_dedupes_within_window(user_dir, monkeypatch):
    """Once reminded, don't re-fire again until the reminder window has passed —
    even though the channel is still stale — so it's a monthly nudge, not daily."""
    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=60)
    just_reminded = now - timedelta(days=2)
    users = [
        {
            "id": "u1",
            "name": USER,
            "channel_rotated_at": _iso(stale),
            "channel_reminder_at": _iso(just_reminded),
        }
    ]
    _stub_users(monkeypatch, users)
    sent = []
    monkeypatch.setattr(svc, "notify_user", lambda *a, **k: sent.append((a, k)))

    assert svc.run_channel_rotation_reminders(now=now) == 0
    assert sent == []


def test_rotation_reminder_resets_after_actual_rotation(user_dir, monkeypatch):
    """A rotation after the last reminder clears the dedup — the timer resets."""
    now = datetime.now(timezone.utc)
    just_rotated = now - timedelta(days=1)
    old_reminder = now - timedelta(days=40)
    users = [
        {
            "id": "u1",
            "name": USER,
            "channel_rotated_at": _iso(just_rotated),
            "channel_reminder_at": _iso(old_reminder),
        }
    ]
    _stub_users(monkeypatch, users)
    sent = []
    monkeypatch.setattr(svc, "notify_user", lambda *a, **k: sent.append((a, k)))

    assert svc.run_channel_rotation_reminders(now=now) == 0
    assert sent == []


def test_notification_cap(user_dir):
    for i in range(55):
        svc.add_notification(USER, f"N{i}", "body", "src", "in_app")
    notifs = svc.get_notifications(USER, limit=200)
    assert len(notifs) <= svc._NOTIF_CAP
