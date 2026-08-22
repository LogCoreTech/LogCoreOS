"""Tests for main._startup_checks() fail-closed behavior on an insecure
SECRET_KEY and on wildcard CORS."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import main
from config import settings


@pytest.fixture(autouse=True)
def _safe_cors(monkeypatch):
    """Every SECRET_KEY-focused test below runs with a real origin configured,
    so it only ever exercises the SECRET_KEY check, not the separate CORS one."""
    monkeypatch.setattr(settings, "allowed_origins", "https://example.com")
    monkeypatch.setattr(settings, "allow_insecure_cors", False)


@pytest.mark.parametrize("bad_key", ["change-me-in-production", ""])
def test_startup_exits_on_insecure_secret_key(brain, monkeypatch, bad_key):
    monkeypatch.setattr(settings, "secret_key", bad_key)
    monkeypatch.setattr(settings, "allow_insecure_secret_key", False)
    with pytest.raises(SystemExit) as exc:
        main._startup_checks()
    assert exc.value.code == 1


@pytest.mark.parametrize("bad_key", ["change-me-in-production", ""])
def test_startup_allows_insecure_key_with_escape_hatch(brain, monkeypatch, bad_key):
    monkeypatch.setattr(settings, "secret_key", bad_key)
    monkeypatch.setattr(settings, "allow_insecure_secret_key", True)
    main._startup_checks()  # must not raise


def test_startup_ok_with_real_key(brain, monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "a-real-strong-secret-key-value")
    monkeypatch.setattr(settings, "allow_insecure_secret_key", False)
    main._startup_checks()  # must not raise


# ---------------------------------------------------------------------------
# Wildcard CORS
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _safe_secret_key(monkeypatch):
    """Every CORS-focused test below runs with a real SECRET_KEY, so it only
    ever exercises the CORS check, not the separate SECRET_KEY one."""
    monkeypatch.setattr(settings, "secret_key", "a-real-strong-secret-key-value")
    monkeypatch.setattr(settings, "allow_insecure_secret_key", False)


def test_startup_falls_back_to_localhost_on_wildcard_cors_with_no_domain(brain, monkeypatch):
    """2026-08-22: no longer refuses to start — that could brick a fresh
    instance before its owner can even reach Admin -> Hosting to configure a
    domain. Falls back to a safe, narrow default instead."""
    monkeypatch.setattr(settings, "allowed_origins", "*")
    monkeypatch.setattr(settings, "allow_insecure_cors", False)
    monkeypatch.setattr(main, "effective_domain_url", lambda: "")
    main._startup_checks()  # must not raise
    assert settings.allowed_origins == "http://localhost:8000,http://127.0.0.1:8000"


def test_startup_trusts_a_configured_hosting_domain_over_wildcard_cors(brain, monkeypatch):
    """DynamicCORSMiddleware._is_allowed() ignores ALLOWED_ORIGINS entirely once
    a real domain is on file — an instance with one configured is already safe
    in practice, so this must not exit, and must not mutate the env var either
    (nothing here needs fixing)."""
    monkeypatch.setattr(settings, "allowed_origins", "*")
    monkeypatch.setattr(settings, "allow_insecure_cors", False)
    monkeypatch.setattr(main, "effective_domain_url", lambda: "https://app.logcoretech.com")
    main._startup_checks()  # must not raise
    assert settings.allowed_origins == "*"


def test_startup_allows_wildcard_cors_with_escape_hatch(brain, monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", "*")
    monkeypatch.setattr(settings, "allow_insecure_cors", True)
    main._startup_checks()  # must not raise


def test_startup_ok_with_real_origin(brain, monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", "https://example.com")
    monkeypatch.setattr(settings, "allow_insecure_cors", False)
    main._startup_checks()  # must not raise


def test_startup_ok_with_empty_origin(brain, monkeypatch):
    """launch.sh writes an empty ALLOWED_ORIGINS on fresh installs (never '*')
    — must not be treated the same as an explicit wildcard."""
    monkeypatch.setattr(settings, "allowed_origins", "")
    monkeypatch.setattr(settings, "allow_insecure_cors", False)
    main._startup_checks()  # must not raise
