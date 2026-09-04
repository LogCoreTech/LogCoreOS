"""ai_settings.py — Admin AI provider configuration: the provider/model/base_url/
key form, the static provider catalog for the picker UI, and the opt-in "Load
Models" live-fetch action. Extracted from auth.py (same mount prefix, so no
frontend URL changes) the way infisical.py/features.py already are.

Search settings (Tavily) stay in auth.py — unrelated concern, even though it
shares the same underlying ai_settings.json file.

Backend never resolves ai_base_url from the catalog at CALL time (see
services/ai_provider.py) — only this router does, at SAVE time. An existing
instance's already-saved settings keep dispatching exactly as before, unchanged,
forever, even if this router is never reopened again.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator

from config import settings
from routers.auth import ai_settings_path, require_admin
from services import ai_provider_catalog as catalog
from services.file_service import read_json, write_json
from services.rate_limiter import rate_limit

router = APIRouter()

_MAX_FETCHED_MODELS = 200  # cap iteration — some providers (OpenRouter) list hundreds
_model_fetch_limit = rate_limit(10, 60)  # stricter than the general admin limit — real network call


class AiSettingsRequest(BaseModel):
    ai_provider: str = "anthropic"
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    azure_endpoint: str = ""
    azure_deployment: str = ""
    azure_api_version: str = ""
    ai_allow_model_fetch: bool = False

    @model_validator(mode="after")
    def _azure_fields_required(self):
        if self.ai_provider == "azure_openai" and not (
            self.azure_endpoint and self.azure_deployment
        ):
            raise ValueError(
                "Azure OpenAI requires both a resource endpoint and a deployment name."
            )
        return self


def _key_set(stored: dict, provider: str) -> bool:
    return bool(
        stored.get("ai_api_key") or (provider == "anthropic" and settings.anthropic_api_key)
    )


def _settings_response(stored: dict) -> dict:
    provider = stored.get("ai_provider", settings.ai_provider)
    return {
        "ai_provider": provider,
        "ai_model": stored.get("ai_model", settings.ai_model),
        "ai_api_key_set": _key_set(stored, provider),
        "ai_base_url": stored.get("ai_base_url", ""),
        "azure_endpoint": stored.get("azure_endpoint", ""),
        "azure_deployment": stored.get("azure_deployment", ""),
        "azure_api_version": stored.get("azure_api_version", ""),
        "ai_allow_model_fetch": stored.get("ai_allow_model_fetch", False),
    }


@router.get("/admin/ai-settings")
def get_ai_settings(current_user: dict = Depends(require_admin)):
    return _settings_response(read_json(ai_settings_path(), default={}))


@router.patch("/admin/ai-settings")
def update_ai_settings(req: AiSettingsRequest, current_user: dict = Depends(require_admin)):
    stored = read_json(ai_settings_path(), default={})
    stored["ai_provider"] = req.ai_provider
    # Server is authoritative for every known provider's base_url — a client-
    # supplied value is only ever honored for "custom" or a not-yet-verified
    # provider. This is the generalized fix for the old Groq preset bug.
    stored["ai_base_url"] = catalog.resolve_base_url(req.ai_provider, req.ai_base_url)
    if req.ai_model:
        stored["ai_model"] = req.ai_model
    if req.ai_api_key:
        stored["ai_api_key"] = req.ai_api_key
    stored["azure_endpoint"] = req.azure_endpoint
    stored["azure_deployment"] = req.azure_deployment
    stored["azure_api_version"] = req.azure_api_version
    stored["ai_allow_model_fetch"] = req.ai_allow_model_fetch
    write_json(ai_settings_path(), stored)
    return _settings_response(stored)


@router.get("/admin/ai-provider-catalog")
def get_ai_provider_catalog(current_user: dict = Depends(require_admin)):
    """Static picker data. Includes default_base_url — these are well-known
    public API endpoints (Groq's, Gemini's, ...), not secrets, and the
    frontend needs them to reconcile an already-saved ai_base_url against the
    right dropdown entry on load. The server still never lets a client
    OVERRIDE a known provider's URL (see resolve_base_url) — only reads it."""
    return {
        "providers": [
            {
                "id": spec.id,
                "label": spec.label,
                "kind": spec.kind,
                "default_base_url": spec.default_base_url,
                "needs_api_key": spec.needs_api_key,
                "docs_verified": spec.docs_verified,
                "static_models": [{"id": m.id, "label": m.label} for m in spec.static_models],
            }
            for spec in catalog.PROVIDERS.values()
        ]
    }


class LoadModelsRequest(BaseModel):
    ai_provider: str
    ai_api_key: str = ""
    ai_base_url: str = ""


class FetchedModel(BaseModel):
    id: str
    display_name: str | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None


class LoadModelsResponse(BaseModel):
    provider: str
    models: list[FetchedModel]
    warning: str | None = None


def _resolve_fetch_key(req: LoadModelsRequest, stored: dict) -> str:
    """The just-typed key wins when present. When blank, the persisted key is
    reused ONLY when the request's provider (and, for custom, base_url) matches
    what's currently saved — never across a provider mismatch. Without this
    guard, an admin testing a new "custom" URL with the key field left blank
    (masked/write-only by design) could have their real, persisted key for a
    DIFFERENT provider silently sent to whatever host they just typed."""
    if req.ai_api_key:
        return req.ai_api_key
    stored_provider = stored.get("ai_provider", "")
    if stored_provider != req.ai_provider:
        return ""
    if req.ai_provider == "custom" and stored.get("ai_base_url", "") != req.ai_base_url:
        return ""
    return stored.get("ai_api_key", "") or (
        settings.anthropic_api_key if req.ai_provider == "anthropic" else ""
    )


@router.post("/admin/ai-settings/models", response_model=LoadModelsResponse)
def load_models(
    req: LoadModelsRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_model_fetch_limit),
):
    stored = read_json(ai_settings_path(), default={})
    if not stored.get("ai_allow_model_fetch", False):
        raise HTTPException(
            403, "Model list fetching is disabled. Enable it in Admin -> AI Settings first."
        )
    if req.ai_provider == "azure_openai":
        raise HTTPException(
            400,
            "Azure OpenAI doesn't support model listing here — its own model-list endpoint "
            "returns base models, not your deployments. Type your deployment name directly.",
        )

    spec = catalog.get_provider(req.ai_provider)
    key = _resolve_fetch_key(req, stored)
    base_url = catalog.resolve_base_url(req.ai_provider, req.ai_base_url)

    if not key and spec.list_requires_key:
        # Without this, an admin switching the picker to a different provider
        # (without saving first) and clicking Load Models before typing a fresh
        # key would fall through to the openai-compatible branch's "ollama"
        # placeholder below — a real cloud provider rejects that fake key, and
        # the resulting auth failure surfaced as an opaque 502 with no hint
        # that a key was ever missing in the first place.
        raise HTTPException(
            400,
            f"{spec.label} requires an API key to list its models — that's a requirement "
            "of their API, not ours. Type one in above (or save your settings with a key "
            "for this provider first), then try again.",
        )

    try:
        if spec.kind == "anthropic":
            import anthropic as _anthropic

            client = _anthropic.Anthropic(api_key=key)
            page = client.models.list(limit=_MAX_FETCHED_MODELS)
            models = [
                FetchedModel(
                    id=m.id,
                    display_name=getattr(m, "display_name", None),
                    max_input_tokens=getattr(m, "max_input_tokens", None),
                    max_output_tokens=getattr(m, "max_tokens", None),
                )
                for m in page
            ]
        else:
            import openai as _openai

            client = _openai.OpenAI(api_key=key or "ollama", base_url=base_url or None)
            page = client.models.list()
            models = []
            for m in page:
                if len(models) >= _MAX_FETCHED_MODELS:
                    break
                models.append(
                    FetchedModel(
                        id=m.id,
                        max_input_tokens=getattr(m, "context_window", None)
                        or getattr(m, "context_length", None),
                    )
                )
    except Exception as exc:
        raise HTTPException(502, f"Could not load models from {spec.label}: {exc}") from None

    warning = None
    if models and all(m.max_input_tokens is None for m in models):
        warning = f"{spec.label} doesn't report model capability data — showing names only."

    return LoadModelsResponse(provider=req.ai_provider, models=models, warning=warning)
