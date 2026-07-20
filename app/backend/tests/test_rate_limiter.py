"""Tests for the in-memory IP-based rate limiter."""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException

import services.rate_limiter as rl


def _req(ip="1.2.3.4", path="/test", forwarded=None):
    req = MagicMock()
    req.client.host = ip
    req.url.path = path
    req.headers.get = lambda k, d=None: (forwarded if k == "X-Forwarded-For" else d)
    return req


@pytest.fixture(autouse=True)
def reset_state():
    rl._hits.clear()
    rl._sweep_n = 0
    yield
    rl._hits.clear()
    rl._sweep_n = 0


# ---------------------------------------------------------------------------
# Basic allow / block
# ---------------------------------------------------------------------------


def test_allows_up_to_limit():
    dep = rl.rate_limit(3, 60)
    for _ in range(3):
        dep(_req())  # must not raise


def test_blocks_when_over_limit():
    dep = rl.rate_limit(2, 60)
    dep(_req())
    dep(_req())
    with pytest.raises(HTTPException) as exc:
        dep(_req())
    assert exc.value.status_code == 429


def test_error_message_is_user_friendly():
    dep = rl.rate_limit(1, 60)
    dep(_req())
    with pytest.raises(HTTPException) as exc:
        dep(_req())
    assert "wait" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# Isolation — different IPs and paths
# ---------------------------------------------------------------------------


def test_different_ips_tracked_separately():
    dep = rl.rate_limit(1, 60)
    dep(_req(ip="1.1.1.1"))
    dep(_req(ip="2.2.2.2"))  # different IP — must not raise


def test_limit_reached_for_one_ip_does_not_affect_another():
    dep = rl.rate_limit(1, 60)
    dep(_req(ip="1.1.1.1"))
    with pytest.raises(HTTPException):
        dep(_req(ip="1.1.1.1"))
    dep(_req(ip="9.9.9.9"))  # unaffected IP — must not raise


def test_different_paths_tracked_separately():
    dep_a = rl.rate_limit(1, 60)
    dep_b = rl.rate_limit(1, 60)
    dep_a(_req(path="/login"))
    dep_b(_req(path="/register"))  # different path — must not raise


def test_shared_bucket_counts_across_paths():
    """An explicit bucket makes distinct paths share one allowance, so /auth/login
    and /auth/token can't be used to double the login-attempt budget (A1)."""
    login = rl.rate_limit(2, 60, bucket="auth-login")
    token = rl.rate_limit(2, 60, bucket="auth-login")
    login(_req(path="/auth/login"))
    token(_req(path="/auth/token"))  # same bucket, same IP → 2 hits used
    with pytest.raises(HTTPException) as exc:
        login(_req(path="/auth/login"))
    assert exc.value.status_code == 429


# ---------------------------------------------------------------------------
# Window expiry
# ---------------------------------------------------------------------------


def test_hits_outside_window_do_not_count(monkeypatch):
    dep = rl.rate_limit(1, 1)  # 1 request per second
    dep(_req())
    # Jump time forward past the window
    t0 = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: t0 + 2)
    dep(_req())  # old hit expired — must not raise


# ---------------------------------------------------------------------------
# IP detection — proxy header handling
# ---------------------------------------------------------------------------


def test_client_ip_ignores_forwarded_when_proxy_untrusted(monkeypatch):
    monkeypatch.setattr(rl.settings, "trust_proxy_headers", False)
    req = _req(ip="10.0.0.1", forwarded="99.99.99.99")
    assert rl._client_ip(req) == "10.0.0.1"


def test_client_ip_uses_forwarded_when_proxy_trusted(monkeypatch):
    monkeypatch.setattr(rl.settings, "trust_proxy_headers", True)
    req = _req(ip="10.0.0.1", forwarded="99.99.99.99")
    assert rl._client_ip(req) == "99.99.99.99"


def test_client_ip_uses_leftmost_forwarded_ip(monkeypatch):
    monkeypatch.setattr(rl.settings, "trust_proxy_headers", True)
    req = _req(ip="10.0.0.1", forwarded="1.1.1.1, 2.2.2.2, 3.3.3.3")
    assert rl._client_ip(req) == "1.1.1.1"


# ---------------------------------------------------------------------------
# Internal sweep
# ---------------------------------------------------------------------------


def test_sweep_removes_stale_entries():
    rl._hits["stale"] = [time.monotonic() - 7200]
    rl._sweep(time.monotonic())
    assert "stale" not in rl._hits


def test_sweep_keeps_recent_entries():
    rl._hits["fresh"] = [time.monotonic()]
    rl._sweep(time.monotonic())
    assert "fresh" in rl._hits
