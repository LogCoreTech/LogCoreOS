"""Tests for services/push_service.py — VAPID subject handling and
subscription-vs-send-failure distinction (2026-08-15)."""

import base64
import json

from config import settings
from services import push_service


def _b64ud(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _jwt_sub(jwt: str) -> str:
    header_b, payload_b, _sig_b = jwt.split(".")
    return json.loads(_b64ud(payload_b))["sub"]


def test_bare_email_subject_gets_mailto_prefix(brain, monkeypatch):
    monkeypatch.setattr(settings, "vapid_subject", "admin@example.com")
    private_key, _pub = push_service._load_or_generate_vapid()
    jwt = push_service._build_vapid_jwt(private_key, "https://push.example.com/abc")
    assert _jwt_sub(jwt) == "mailto:admin@example.com"


def test_https_subject_used_as_is_not_double_wrapped(brain, monkeypatch):
    monkeypatch.setattr(settings, "vapid_subject", "https://logcore.example.com")
    private_key, _pub = push_service._load_or_generate_vapid()
    jwt = push_service._build_vapid_jwt(private_key, "https://push.example.com/abc")
    assert _jwt_sub(jwt) == "https://logcore.example.com"


def test_mailto_subject_used_as_is_not_double_wrapped(brain, monkeypatch):
    monkeypatch.setattr(settings, "vapid_subject", "mailto:admin@example.com")
    private_key, _pub = push_service._load_or_generate_vapid()
    jwt = push_service._build_vapid_jwt(private_key, "https://push.example.com/abc")
    assert _jwt_sub(jwt) == "mailto:admin@example.com"


def test_send_push_returns_false_with_no_subscription(brain):
    assert push_service.send_push("NoSubUser", "Title", "Body") is False


def test_subscription_round_trip(brain):
    assert push_service.get_subscription("Alice") is None
    push_service.save_subscription(
        "Alice", {"endpoint": "https://push.example.com/x", "keys": {"p256dh": "a", "auth": "b"}}
    )
    sub = push_service.get_subscription("Alice")
    assert sub["endpoint"] == "https://push.example.com/x"
    push_service.delete_subscription("Alice")
    assert push_service.get_subscription("Alice") is None
