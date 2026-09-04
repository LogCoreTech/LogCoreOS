"""ai_provider_catalog.py — static data describing every named AI provider the
Admin -> AI Settings picker offers, plus the models each ships with out of the
box (no fetch needed). Pure data + pure functions, no I/O, no network.

This is app-defined reference data (like dashboard_blocks/agent_schemas.py or
constants.js's ALL_MODULES), not admin-editable Brain data — it belongs in code,
not ai_settings.json.

docs_verified=False entries have a default_base_url of None deliberately: their
base URL was not independently confirmed against the provider's own current docs
this session, so the frontend renders them exactly like "custom" (a free-text URL
field) rather than shipping a possibly-wrong hardcoded address. Flip
docs_verified=True and fill in default_base_url once confirmed.
"""

from dataclasses import dataclass, field
from typing import Literal

ProviderKind = Literal["anthropic", "openai_compatible", "azure_openai", "custom"]


@dataclass(frozen=True)
class StaticModel:
    id: str
    label: str | None = None  # None = display the id verbatim


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    kind: ProviderKind
    default_base_url: str | None = None  # None => frontend shows a free-text base_url field
    needs_api_key: bool = True
    list_requires_key: bool = True  # False only for providers with a public model list
    docs_verified: bool = True
    static_models: tuple[StaticModel, ...] = field(default_factory=tuple)


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        id="anthropic",
        label="Anthropic",
        kind="anthropic",
        static_models=(
            StaticModel("claude-sonnet-4-6"),
            StaticModel("claude-haiku-4-6"),
        ),
    ),
    "openai": ProviderSpec(
        id="openai",
        label="OpenAI",
        kind="openai_compatible",
        static_models=(StaticModel("gpt-4o"),),
    ),
    "azure_openai": ProviderSpec(
        id="azure_openai",
        label="Azure OpenAI",
        kind="azure_openai",
        needs_api_key=True,
    ),
    "groq": ProviderSpec(
        id="groq",
        label="Groq",
        kind="openai_compatible",
        default_base_url="https://api.groq.com/openai/v1",
        static_models=(StaticModel("llama-3.3-70b-versatile"),),
    ),
    "gemini": ProviderSpec(
        id="gemini",
        label="Gemini",
        kind="openai_compatible",
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        static_models=(StaticModel("gemini-2.0-flash"),),
    ),
    "mistral": ProviderSpec(
        id="mistral",
        label="Mistral",
        kind="openai_compatible",
        default_base_url="https://api.mistral.ai/v1",
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        label="DeepSeek",
        kind="openai_compatible",
        default_base_url="https://api.deepseek.com",
    ),
    "xai": ProviderSpec(
        id="xai",
        label="xAI (Grok)",
        kind="openai_compatible",
        default_base_url="https://api.x.ai/v1",
    ),
    "cerebras": ProviderSpec(
        id="cerebras",
        label="Cerebras",
        kind="openai_compatible",
        default_base_url="https://api.cerebras.ai/v1",
    ),
    "together": ProviderSpec(
        id="together",
        label="Together AI",
        kind="openai_compatible",
        default_base_url="https://api.together.xyz/v1",
    ),
    "fireworks": ProviderSpec(
        id="fireworks",
        label="Fireworks AI",
        kind="openai_compatible",
        default_base_url="https://api.fireworks.ai/inference/v1",
    ),
    "openrouter": ProviderSpec(
        id="openrouter",
        label="OpenRouter",
        kind="openai_compatible",
        default_base_url="https://openrouter.ai/api/v1",
        list_requires_key=False,
    ),
    "ollama": ProviderSpec(
        id="ollama",
        label="Ollama (local)",
        kind="openai_compatible",
        default_base_url="http://localhost:11434/v1",
        needs_api_key=False,
        list_requires_key=False,
        static_models=(StaticModel("llama3.2"),),
    ),
    "lmstudio": ProviderSpec(
        id="lmstudio",
        label="LM Studio (local)",
        kind="openai_compatible",
        default_base_url="http://localhost:1234/v1",
        needs_api_key=False,
        list_requires_key=False,
    ),
    "vllm": ProviderSpec(
        id="vllm",
        label="vLLM (local)",
        kind="openai_compatible",
        default_base_url="http://localhost:8000/v1",
        needs_api_key=False,
        list_requires_key=False,
    ),
    # Not independently verified this session — no default_base_url until confirmed
    # against each provider's own current docs. Render identically to "custom" until then.
    "deepinfra": ProviderSpec(
        id="deepinfra", label="DeepInfra", kind="openai_compatible", docs_verified=False
    ),
    "novita": ProviderSpec(
        id="novita", label="Novita AI", kind="openai_compatible", docs_verified=False
    ),
    "sambanova": ProviderSpec(
        id="sambanova", label="SambaNova", kind="openai_compatible", docs_verified=False
    ),
    "hyperbolic": ProviderSpec(
        id="hyperbolic", label="Hyperbolic", kind="openai_compatible", docs_verified=False
    ),
    "baseten": ProviderSpec(
        id="baseten", label="Baseten", kind="openai_compatible", docs_verified=False
    ),
    "llamacpp": ProviderSpec(
        id="llamacpp",
        label="llama.cpp (local)",
        kind="openai_compatible",
        needs_api_key=False,
        list_requires_key=False,
        docs_verified=False,
    ),
    "text_gen_webui": ProviderSpec(
        id="text_gen_webui",
        label="text-generation-webui (local)",
        kind="openai_compatible",
        needs_api_key=False,
        list_requires_key=False,
        docs_verified=False,
    ),
    "koboldcpp": ProviderSpec(
        id="koboldcpp",
        label="KoboldCpp (local)",
        kind="openai_compatible",
        needs_api_key=False,
        list_requires_key=False,
        docs_verified=False,
    ),
    "janai": ProviderSpec(
        id="janai",
        label="Jan.ai (local)",
        kind="openai_compatible",
        needs_api_key=False,
        list_requires_key=False,
        docs_verified=False,
    ),
    "custom": ProviderSpec(
        id="custom",
        label="Custom (OpenAI-compatible)",
        kind="custom",
        needs_api_key=False,
        list_requires_key=False,
    ),
}


def get_provider(provider_id: str) -> ProviderSpec:
    """Unknown ids resolve to "custom" — the same escape-hatch behavior a
    not-yet-docs_verified provider already gets, never a KeyError."""
    return PROVIDERS.get(provider_id, PROVIDERS["custom"])


def resolve_base_url(provider_id: str, requested_base_url: str) -> str:
    """The server is authoritative for every known provider's base_url — a
    client-supplied value is only ever honored for "custom" or a
    not-yet-docs_verified provider (both have default_base_url=None)."""
    spec = get_provider(provider_id)
    if spec.default_base_url is not None:
        return spec.default_base_url
    return requested_base_url
