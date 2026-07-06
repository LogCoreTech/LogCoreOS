"""Shared fixtures for all backend tests."""

import sys
from pathlib import Path

# Add app/backend to sys.path so imports resolve without package install
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


@pytest.fixture()
def brain(tmp_path, monkeypatch):
    """Patch settings.brain_path to an isolated temp directory."""
    from config import settings

    monkeypatch.setattr(settings, "brain_path", tmp_path / "brain")
    (tmp_path / "brain" / "_system").mkdir(parents=True, exist_ok=True)
    return tmp_path / "brain"
