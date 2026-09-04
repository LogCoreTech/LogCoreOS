"""Tests for ai_provider.py's config merge — specifically the demo-mode cost guard —
plus dispatch routing (including the new Azure OpenAI branch)."""

import sys
import types

import pytest

from config import settings
from services.ai_provider import _dispatch_kind, _get_config, is_ai_configured


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


def test_dispatch_kind_resolves_known_providers():
    assert _dispatch_kind("anthropic") == "anthropic"
    assert _dispatch_kind("azure_openai") == "azure_openai"
    assert _dispatch_kind("groq") == "openai_compatible"
    assert _dispatch_kind("custom") == "custom"


def test_dispatch_kind_raises_for_a_genuinely_unknown_provider():
    """Unlike catalog.get_provider() (which resolves unknowns to "custom" for
    settings storage/display), actually dispatching a request must still fail
    loudly on a bogus config value rather than silently hitting some endpoint."""
    with pytest.raises(ValueError, match="not-a-real-provider"):
        _dispatch_kind("not-a-real-provider")


def test_is_ai_configured_azure_requires_all_three_fields(brain, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "azure_openai")
    from services.file_service import write_json

    write_json(
        settings.brain_path / "ai_settings.json",
        {
            "ai_provider": "azure_openai",
            "ai_api_key": "key",
            "azure_endpoint": "https://x.openai.azure.com",
            # azure_deployment deliberately missing
        },
    )
    assert is_ai_configured() is False

    write_json(
        settings.brain_path / "ai_settings.json",
        {
            "ai_provider": "azure_openai",
            "ai_api_key": "key",
            "azure_endpoint": "https://x.openai.azure.com",
            "azure_deployment": "my-deployment",
        },
    )
    assert is_ai_configured() is True


def test_azure_dispatch_constructs_azure_openai_client_not_generic_openai(brain, monkeypatch):
    """The Azure branch must use openai.AzureOpenAI(azure_endpoint=...,
    azure_deployment=..., api_version=...), not a generic base_url client."""
    from services.ai_provider import _dispatch
    from services.file_service import write_json

    write_json(
        settings.brain_path / "ai_settings.json",
        {
            "ai_provider": "azure_openai",
            "ai_api_key": "azure-key",
            "azure_endpoint": "https://x.openai.azure.com",
            "azure_deployment": "my-deployment",
            "azure_api_version": "2024-08-01",
        },
    )

    captured = {}

    class _FakeMessage:
        content = "hi"

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]
        usage = types.SimpleNamespace(prompt_tokens=10, completion_tokens=5)

    class _FakeChatCompletions:
        def create(self, **kwargs):
            captured["create_kwargs"] = kwargs
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeChatCompletions()

    class _FakeAzureClient:
        chat = _FakeChat()

    class _FakeOpenAIModule(types.SimpleNamespace):
        def AzureOpenAI(self, **kwargs):
            captured["client_kwargs"] = kwargs
            return _FakeAzureClient()

    monkeypatch.setitem(sys.modules, "openai", _FakeOpenAIModule())

    text, in_tok, out_tok = _dispatch("system prompt", [{"role": "user", "content": "hi"}], 100)

    assert text == "hi"
    assert captured["client_kwargs"]["azure_endpoint"] == "https://x.openai.azure.com"
    assert captured["client_kwargs"]["azure_deployment"] == "my-deployment"
    assert captured["client_kwargs"]["api_version"] == "2024-08-01"
    assert captured["create_kwargs"]["model"] == "my-deployment"
