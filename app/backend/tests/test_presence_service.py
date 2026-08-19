"""Tests for presence_service — app-wide online/offline tracking (2026-08-17),
generalized from agent_service.py's chat-only presence pattern."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import presence_service as svc
from services.file_service import write_json


def test_is_online_false_before_any_ping(brain):
    assert svc.is_online("Nobody") is False


def test_record_presence_then_is_online(brain):
    svc.record_presence("Alice")
    assert svc.is_online("Alice") is True


def test_is_online_false_once_stale(brain):
    svc.record_presence("Alice")
    stale = (
        datetime.now(timezone.utc) - timedelta(seconds=svc._STALE_AFTER_SECONDS + 5)
    ).isoformat()
    write_json(svc._presence_path("Alice"), {"seen_at": stale})
    assert svc.is_online("Alice") is False


def test_presence_is_per_user(brain):
    svc.record_presence("Alice")
    assert svc.is_online("Alice") is True
    assert svc.is_online("Bob") is False


def test_last_seen_iso_none_before_any_ping(brain):
    assert svc.last_seen_iso("Nobody") is None


def test_last_seen_iso_returns_raw_timestamp_even_when_stale(brain):
    # Unlike is_online (a computed boolean), last_seen_iso is the raw
    # timestamp regardless of staleness — the frontend's "last seen X ago"
    # display needs the real value even long after the 90s online window.
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_json(svc._presence_path("Alice"), {"seen_at": stale})
    assert svc.is_online("Alice") is False
    assert svc.last_seen_iso("Alice") == stale
