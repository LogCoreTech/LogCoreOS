"""Tests for services/ai_provider_catalog.py — pure data + pure functions, no
brain/network fixtures needed."""

from services.ai_provider_catalog import PROVIDERS, get_provider, resolve_base_url


def test_every_key_matches_its_own_id():
    for key, spec in PROVIDERS.items():
        assert key == spec.id


def test_every_verified_provider_needing_a_url_has_one():
    """anthropic/azure_openai/custom don't need a base_url (native SDK, its own
    endpoint field, or genuinely unknown-a-priori respectively); "openai" is a
    deliberate exception too — None there means "use the SDK's real native
    default," not "unverified." Every other docs_verified provider must have a
    real default_base_url, or the "verified" flag is a lie."""
    exempt = {"anthropic", "azure_openai", "custom", "openai"}
    for spec in PROVIDERS.values():
        if spec.id in exempt:
            continue
        if spec.docs_verified:
            assert spec.default_base_url, f"{spec.id} is docs_verified but has no base_url"


def test_unverified_providers_have_no_base_url():
    for spec in PROVIDERS.values():
        if not spec.docs_verified:
            assert spec.default_base_url is None


def test_get_provider_unknown_id_falls_back_to_custom():
    assert get_provider("something-made-up").id == "custom"


def test_get_provider_known_id():
    assert get_provider("groq").label == "Groq"


def test_resolve_base_url_known_provider_ignores_client_value():
    assert resolve_base_url("groq", "https://evil.example.com") == "https://api.groq.com/openai/v1"


def test_resolve_base_url_custom_honors_client_value():
    assert (
        resolve_base_url("custom", "http://my-own-proxy:8080/v1") == "http://my-own-proxy:8080/v1"
    )


def test_resolve_base_url_unverified_provider_honors_client_value():
    """Same behavior as custom until someone confirms and fills in a real URL."""
    assert resolve_base_url("deepinfra", "https://api.deepinfra.com/v1/openai") == (
        "https://api.deepinfra.com/v1/openai"
    )


def test_resolve_base_url_unknown_provider_falls_back_to_custom_behavior():
    assert resolve_base_url("nonexistent", "http://whatever") == "http://whatever"
