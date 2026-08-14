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


def test_startup_exits_on_wildcard_cors(brain, monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", "*")
    monkeypatch.setattr(settings, "allow_insecure_cors", False)
    with pytest.raises(SystemExit) as exc:
        main._startup_checks()
    assert exc.value.code == 1


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
