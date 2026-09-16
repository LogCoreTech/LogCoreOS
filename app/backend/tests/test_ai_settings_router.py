"""Tests for routers/ai_settings.py — the extracted-and-widened AI provider
settings endpoints. Endpoint functions called directly, bypassing Depends(...),
matching this suite's established convention (see test_features.py).
"""

import sys
import types

import pytest
from fastapi import HTTPException

from routers.ai_settings import (
    AiSettingsRequest,
    LoadModelsRequest,
    _reject_ssrf_base_url,
    get_ai_provider_catalog,
    get_ai_settings,
    load_models,
    update_ai_settings,
)
from services import ai_provider_catalog as catalog
from services import auth_service, net_safety
from services.file_service import read_json, write_json


def _admin(brain):
    return auth_service.create_user("admin@example.com", "password123", "Admin", role="admin")


def _settings_path(brain):
    return brain / "ai_settings.json"


def test_patch_groq_server_resolves_base_url_regardless_of_request(brain):
    admin = _admin(brain)
    req = AiSettingsRequest(ai_provider="groq", ai_base_url="https://evil.example.com")
    result = update_ai_settings(req, admin)
    assert result["ai_base_url"] == "https://api.groq.com/openai/v1"

    fresh = get_ai_settings(admin)
    assert fresh["ai_base_url"] == "https://api.groq.com/openai/v1"


def test_patch_custom_honors_client_base_url(brain):
    admin = _admin(brain)
    req = AiSettingsRequest(ai_provider="custom", ai_base_url="http://my-proxy:9000/v1")
    result = update_ai_settings(req, admin)
    assert result["ai_base_url"] == "http://my-proxy:9000/v1"


def test_patch_azure_missing_deployment_rejected():
    with pytest.raises(ValueError):
        AiSettingsRequest(ai_provider="azure_openai", azure_endpoint="https://x.openai.azure.com")


def test_patch_azure_with_both_fields_accepted(brain):
    admin = _admin(brain)
    req = AiSettingsRequest(
        ai_provider="azure_openai",
        azure_endpoint="https://x.openai.azure.com",
        azure_deployment="my-deployment",
    )
    result = update_ai_settings(req, admin)
    assert result["ai_provider"] == "azure_openai"


def test_blank_api_key_leaves_previously_saved_key_untouched(brain):
    admin = _admin(brain)
    update_ai_settings(AiSettingsRequest(ai_provider="anthropic", ai_api_key="sk-real-key"), admin)
    result = update_ai_settings(AiSettingsRequest(ai_provider="anthropic", ai_api_key=""), admin)
    assert result["ai_api_key_set"] is True
    assert read_json(_settings_path(brain))["ai_api_key"] == "sk-real-key"


def test_fetch_toggle_defaults_false_on_a_brand_new_instance(brain):
    admin = _admin(brain)
    assert get_ai_settings(admin)["ai_allow_model_fetch"] is False


def test_load_models_403s_when_toggle_is_off(brain):
    admin = _admin(brain)
    with pytest.raises(HTTPException) as exc:
        load_models(LoadModelsRequest(ai_provider="anthropic"), admin)
    assert exc.value.status_code == 403


def test_load_models_400s_for_azure_regardless_of_toggle(brain):
    admin = _admin(brain)
    update_ai_settings(AiSettingsRequest(ai_provider="anthropic", ai_allow_model_fetch=True), admin)
    with pytest.raises(HTTPException) as exc:
        load_models(LoadModelsRequest(ai_provider="azure_openai"), admin)
    assert exc.value.status_code == 400


class _FakeAnthropicModel:
    def __init__(self, id, max_input_tokens=None, max_tokens=None, display_name=None):
        self.id = id
        self.max_input_tokens = max_input_tokens
        self.max_tokens = max_tokens
        self.display_name = display_name


def _install_fake_anthropic(monkeypatch, models, capture=None):
    fake_client = types.SimpleNamespace()
    fake_client.models = types.SimpleNamespace(
        list=lambda limit=None: (capture.append(True) if capture is not None else None) or models
    )

    class _FakeAnthropicModule(types.SimpleNamespace):
        def Anthropic(self, api_key=None):
            if capture is not None:
                capture.append(api_key)
            return fake_client

    monkeypatch.setitem(sys.modules, "anthropic", _FakeAnthropicModule())


def test_load_models_renders_real_fetched_spec_data(brain, monkeypatch):
    admin = _admin(brain)
    update_ai_settings(AiSettingsRequest(ai_provider="anthropic", ai_allow_model_fetch=True), admin)
    models = [
        _FakeAnthropicModel("claude-sonnet-4-6", max_input_tokens=200000, max_tokens=8192),
        _FakeAnthropicModel("claude-haiku-4-6", max_input_tokens=None, max_tokens=None),
    ]
    _install_fake_anthropic(monkeypatch, models)

    result = load_models(LoadModelsRequest(ai_provider="anthropic", ai_api_key="sk-test"), admin)

    assert result.provider == "anthropic"
    assert result.models[0].max_input_tokens == 200000
    assert result.models[1].max_input_tokens is None


def test_load_models_never_leaks_a_different_providers_saved_key(brain, monkeypatch):
    """The cross-provider key-leak guard: a persisted Anthropic key must never
    be sent to a fetch request for a different provider when that request's
    own key field is left blank. A provider that genuinely needs a key (like
    Groq) now gets a clear 400 instead of the request going out at all — see
    test_load_models_no_key_gives_clear_400_not_a_confusing_502 below, the
    real bug this replaced (silently trying the "ollama" placeholder against
    a real cloud provider, surfacing as an opaque 502)."""
    admin = _admin(brain)
    update_ai_settings(
        AiSettingsRequest(
            ai_provider="anthropic", ai_api_key="sk-real-anthropic-key", ai_allow_model_fetch=True
        ),
        admin,
    )

    captured_keys = []

    fake_openai_client = types.SimpleNamespace(models=types.SimpleNamespace(list=lambda: []))

    class _FakeOpenAIModule(types.SimpleNamespace):
        def OpenAI(self, api_key=None, base_url=None):
            captured_keys.append(api_key)
            return fake_openai_client

    monkeypatch.setitem(sys.modules, "openai", _FakeOpenAIModule())

    # Request is for "groq", not the persisted "anthropic" — blank key must NOT
    # fall back to the real Anthropic secret. Groq needs a key to list models,
    # so this now 400s before ever constructing a client at all — the real
    # Anthropic secret never even risks going out under a different provider's
    # name.
    with pytest.raises(HTTPException) as exc:
        load_models(LoadModelsRequest(ai_provider="groq", ai_api_key=""), admin)
    assert exc.value.status_code == 400
    assert captured_keys == []
    assert "sk-real-anthropic-key" not in str(exc.value.detail)


def test_load_models_no_key_gives_clear_400_not_a_confusing_502(brain, monkeypatch):
    """Real reported bug: switching the picker to a different provider without
    saving, then clicking Load Models before typing a fresh key, used to fall
    through to the openai-compatible branch's "ollama" placeholder — a real
    cloud provider rejects that fake key, and the failure surfaced as an
    opaque 502 with no hint a key was ever missing."""
    admin = _admin(brain)
    update_ai_settings(AiSettingsRequest(ai_provider="anthropic", ai_allow_model_fetch=True), admin)

    with pytest.raises(HTTPException) as exc:
        load_models(LoadModelsRequest(ai_provider="mistral", ai_api_key=""), admin)
    assert exc.value.status_code == 400
    assert "Mistral" in exc.value.detail


def test_load_models_local_runner_with_no_key_still_uses_ollama_placeholder(brain, monkeypatch):
    """Providers that don't need a key at all (local runners) must be
    unaffected by the new 400 guard above — they still fall back to the
    existing "ollama" placeholder value, since their own OpenAI-compatible
    shim doesn't actually validate it."""
    admin = _admin(brain)
    update_ai_settings(AiSettingsRequest(ai_provider="ollama", ai_allow_model_fetch=True), admin)

    captured_keys = []
    fake_openai_client = types.SimpleNamespace(models=types.SimpleNamespace(list=lambda: []))

    class _FakeOpenAIModule(types.SimpleNamespace):
        def OpenAI(self, api_key=None, base_url=None):
            captured_keys.append(api_key)
            return fake_openai_client

    monkeypatch.setitem(sys.modules, "openai", _FakeOpenAIModule())

    load_models(LoadModelsRequest(ai_provider="ollama", ai_api_key=""), admin)
    assert captured_keys == ["ollama"]


def test_backward_compat_old_openai_plus_groq_url_shape_still_works(brain):
    """A pre-upgrade ai_settings.json saved via the OLD generic "openai" +
    base_url shape must keep dispatching correctly with zero code changes in
    ai_provider.py — this router never rewrites it until the admin re-saves."""
    write_json(
        _settings_path(brain),
        {"ai_provider": "openai", "ai_base_url": "https://api.groq.com/openai/v1"},
    )
    admin = _admin(brain)
    result = get_ai_settings(admin)
    assert result["ai_provider"] == "openai"
    assert result["ai_base_url"] == "https://api.groq.com/openai/v1"


# ---------------------------------------------------------------------------
# S7 fix (2026-09-08): SSRF guard on the Load Models live fetch. For "custom"
# and any not-yet-docs_verified provider, resolve_base_url() honors the
# admin-supplied ai_base_url verbatim — _reject_ssrf_base_url must then
# reject anything that resolves to a private/internal address, the same way
# push_service._validate_push_endpoint already does for push endpoints,
# except for the documented local-runner providers.
# ---------------------------------------------------------------------------


def _boom(*_a, **_k):
    raise AssertionError("socket.getaddrinfo should not have been called")


def test_reject_ssrf_base_url_blocks_custom_provider_resolving_privately(monkeypatch):
    monkeypatch.setattr(
        net_safety.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("10.0.0.5", 0))],
    )
    spec = catalog.get_provider("custom")
    with pytest.raises(HTTPException) as exc:
        _reject_ssrf_base_url("custom", spec, "http://internal.example.com:8080/v1")
    assert exc.value.status_code == 400
    assert "non-public" in exc.value.detail


def test_reject_ssrf_base_url_blocks_unverified_provider_resolving_to_cloud_metadata(monkeypatch):
    monkeypatch.setattr(
        net_safety.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("169.254.169.254", 0))],
    )
    spec = catalog.get_provider("deepinfra")
    with pytest.raises(HTTPException) as exc:
        _reject_ssrf_base_url("deepinfra", spec, "http://metadata.example.com/v1")
    assert exc.value.status_code == 400


def test_reject_ssrf_base_url_blocks_unresolvable_hostname(monkeypatch):
    def fake_getaddrinfo(*a, **k):
        raise net_safety.socket.gaierror("simulated DNS failure")

    monkeypatch.setattr(net_safety.socket, "getaddrinfo", fake_getaddrinfo)
    spec = catalog.get_provider("custom")
    with pytest.raises(HTTPException) as exc:
        _reject_ssrf_base_url("custom", spec, "https://nowhere.example.invalid/v1")
    assert exc.value.status_code == 400
    assert "resolved" in exc.value.detail


def test_reject_ssrf_base_url_rejects_url_with_no_hostname():
    spec = catalog.get_provider("custom")
    with pytest.raises(HTTPException) as exc:
        _reject_ssrf_base_url("custom", spec, "not-a-real-url")
    assert exc.value.status_code == 400
    assert "hostname" in exc.value.detail


def test_reject_ssrf_base_url_allows_known_local_runner_resolving_privately(monkeypatch):
    """llama.cpp/text-generation-webui/KoboldCpp/Jan.ai are docs_verified=False
    (no single standard port, so no hardcoded default_base_url), but they're
    still meant to run on localhost — a resolved private/loopback address for
    one of these specific ids must NOT be treated as SSRF."""
    monkeypatch.setattr(
        net_safety.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("127.0.0.1", 0))],
    )
    spec = catalog.get_provider("llamacpp")
    _reject_ssrf_base_url("llamacpp", spec, "http://localhost:8080/v1")  # must not raise


def test_reject_ssrf_base_url_skips_known_verified_provider_entirely(monkeypatch):
    """A known/verified provider's base_url is the server's own hardcoded
    default (resolve_base_url ignores client input for it entirely) — the
    guard must not even attempt to resolve a hostname for it."""
    monkeypatch.setattr(net_safety.socket, "getaddrinfo", _boom)
    spec = catalog.get_provider("groq")
    _reject_ssrf_base_url("groq", spec, "https://api.groq.com/openai/v1")  # must not raise


def test_reject_ssrf_base_url_skips_anthropic_even_with_private_looking_base_url(monkeypatch):
    """base_url isn't even used on load_models' anthropic branch — must not
    block (or need to resolve) it regardless of its value."""
    monkeypatch.setattr(net_safety.socket, "getaddrinfo", _boom)
    spec = catalog.get_provider("anthropic")
    _reject_ssrf_base_url("anthropic", spec, "http://169.254.169.254/")  # must not raise


def test_reject_ssrf_base_url_skips_empty_base_url(monkeypatch):
    monkeypatch.setattr(net_safety.socket, "getaddrinfo", _boom)
    spec = catalog.get_provider("custom")
    _reject_ssrf_base_url("custom", spec, "")  # must not raise


def test_load_models_end_to_end_rejects_custom_provider_pointed_at_internal_host(
    brain, monkeypatch
):
    admin = _admin(brain)
    update_ai_settings(AiSettingsRequest(ai_provider="custom", ai_allow_model_fetch=True), admin)
    monkeypatch.setattr(
        net_safety.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("10.0.0.5", 0))],
    )
    with pytest.raises(HTTPException) as exc:
        load_models(
            LoadModelsRequest(ai_provider="custom", ai_base_url="http://internal.example.com/v1"),
            admin,
        )
    assert exc.value.status_code == 400
    assert "non-public" in exc.value.detail


def test_catalog_exposes_default_base_url_for_frontend_reconciliation(brain):
    """default_base_url is public API-endpoint info, not a secret — the frontend
    needs it to reconcile an already-saved ai_base_url against the right
    dropdown entry (e.g. an old-shape "openai" + Groq's URL -> select Groq)."""
    admin = _admin(brain)
    catalog = get_ai_provider_catalog(admin)
    by_id = {p["id"]: p for p in catalog["providers"]}
    assert by_id["groq"]["default_base_url"] == "https://api.groq.com/openai/v1"
    assert by_id["custom"]["default_base_url"] is None
    for p in catalog["providers"]:
        assert "id" in p and "label" in p and "kind" in p
