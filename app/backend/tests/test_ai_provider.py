"""Tests for ai_provider.py's config merge — specifically the demo-mode cost guard."""

from config import settings
from services.ai_provider import _get_config


def test_demo_mode_forces_the_demo_model(brain, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    monkeypatch.setattr(settings, "ai_model", "claude-sonnet-4-6")
    monkeypatch.setattr(settings, "demo_ai_model", "claude-haiku-4-6")

    assert _get_config()["ai_model"] == "claude-haiku-4-6"


def test_demo_mode_overrides_an_admin_configured_runtime_model(brain, monkeypatch):
    """The whole point: an admin can't accidentally leave demo cost protection off
    by picking a different model in Admin -> AI Settings (brain/ai_settings.json)."""
    from services.file_service import write_json

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    monkeypatch.setattr(settings, "demo_ai_model", "claude-haiku-4-6")
    write_json(settings.brain_path / "ai_settings.json", {"ai_model": "claude-opus-4-6"})

    assert _get_config()["ai_model"] == "claude-haiku-4-6"


def test_demo_mode_off_leaves_the_configured_model_untouched(brain, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    monkeypatch.setattr(settings, "ai_model", "claude-sonnet-4-6")

    assert _get_config()["ai_model"] == "claude-sonnet-4-6"


def test_demo_mode_does_not_override_a_non_anthropic_provider(brain, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "ai_model", "gpt-4o")
    monkeypatch.setattr(settings, "demo_ai_model", "claude-haiku-4-6")

    assert _get_config()["ai_model"] == "gpt-4o"
