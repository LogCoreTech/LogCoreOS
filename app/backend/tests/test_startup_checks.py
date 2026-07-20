"""Tests for main._startup_checks() fail-closed behavior on an insecure SECRET_KEY."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import main
from config import settings


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
