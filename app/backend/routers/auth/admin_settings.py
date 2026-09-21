"""Instance-wide admin settings — registration/workspace/session settings,
search (Tavily) settings, hosting settings, and the automation API token —
split out of the old routers/auth.py. See routers/auth/__init__.py's
docstring for the full rationale of this package split.

Infisical settings live in their own routers/infisical.py, mounted at the
same "/api/v1/auth" prefix — they were never part of this file."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from config import settings
from services import auth_service, automations_config
from services.file_service import brain_path, read_json, write_json
from services.rate_limiter import rate_limit

from .deps import _VALID_WORKSPACES, _admin_limit, require_admin

router = APIRouter()

# ---------------------------------------------------------------------------
# Admin — AI provider settings live in routers/ai_settings.py (same mount
# prefix, so URLs are unchanged) — ai_settings_path() stays here since
# SearchSettingsRequest below shares the same underlying file.
# ---------------------------------------------------------------------------


def ai_settings_path() -> Path:
    # A function, not a module-level constant: brain_path() must be read fresh
    # on every call, not frozen at import time — a bare `X = brain_path() / …`
    # here would bind to whatever settings.brain_path was when this module was
    # FIRST imported, before any test fixture (or, in principle, any other
    # future re-pointing of the brain path) ever gets a chance to apply. See
    # routers/setup.py's TEMPLATE_PATH for the exact same bug class, found and
    # left unfixed there 2026-09-01 — fixed here since new tests hit it directly.
    return brain_path() / "ai_settings.json"


class SearchSettingsRequest(BaseModel):
    tavily_api_key: str = ""


@router.get("/admin/search-settings")
def get_search_settings(current_user: dict = Depends(require_admin)):
    stored = read_json(ai_settings_path(), default={})
    key_set = bool(stored.get("tavily_api_key") or settings.tavily_api_key)
    return {"tavily_key_set": key_set}


@router.patch("/admin/search-settings")
def update_search_settings(
    req: SearchSettingsRequest,
    current_user: dict = Depends(require_admin),
):
    stored = read_json(ai_settings_path(), default={})
    if req.tavily_api_key:
        stored["tavily_api_key"] = req.tavily_api_key
    write_json(ai_settings_path(), stored)
    key_set = bool(stored.get("tavily_api_key") or settings.tavily_api_key)
    return {"tavily_key_set": key_set}


# ---------------------------------------------------------------------------
# Admin — automation token (n8n -> LogCore write API)
#
# Deliberately lives here, not inside module_packages/assets/backend/router.py
# (where these two endpoints originally lived, before assets/ converted
# 2026-08-27) — the token itself (automations_config.py) is core and shared
# by BOTH Assets' and Contacts' own automation APIs, and this is the ONLY
# admin-facing way to view/rotate it (Hosting.jsx's n8n card calls it
# directly). Leaving it inside Assets' own router would mean uninstalling
# Assets (optional, not locked) silently took away the admin's only way to
# manage a token Contacts' automation API still depends on — found during
# Assets' own conversion research, fixed as part of it rather than carried
# forward silently, matching this project's own standing rule for exactly
# this class of gap.
# ---------------------------------------------------------------------------

_automation_token_limit = rate_limit(30, 60)


@router.get("/admin/automation-token")
def get_automation_token(current_user: dict = Depends(require_admin)):
    return {"token": automations_config.get_api_token()}


@router.post("/admin/automation-token/rotate")
def rotate_automation_token(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_automation_token_limit),
):
    return {"token": automations_config.rotate_api_token()}


# ---------------------------------------------------------------------------
# Admin — hosting settings
# ---------------------------------------------------------------------------

_HOSTING_SETTINGS_PATH = brain_path() / "hosting.json"


class HostingSettingsRequest(BaseModel):
    cookie_secure: bool
    trust_proxy_headers: bool
    domain_url: str = ""
    proxy_type: str = ""  # "cloudflare" | "nginx" | ""
    tunnel_token: str = ""  # Cloudflare tunnel token; empty = don't overwrite stored value


@router.get("/admin/hosting-settings")
def get_hosting_settings(current_user: dict = Depends(require_admin)):
    stored = read_json(_HOSTING_SETTINGS_PATH, default={})
    return {
        "cookie_secure": stored.get("cookie_secure", settings.cookie_secure),
        "trust_proxy_headers": stored.get("trust_proxy_headers", settings.trust_proxy_headers),
        "domain_url": stored.get("domain_url", ""),
        "proxy_type": stored.get("proxy_type", ""),
        "tunnel_token_set": bool(stored.get("tunnel_token", "")),
    }


@router.patch("/admin/hosting-settings")
def update_hosting_settings(
    req: HostingSettingsRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    stored = read_json(_HOSTING_SETTINGS_PATH, default={})
    stored["cookie_secure"] = req.cookie_secure
    stored["trust_proxy_headers"] = req.trust_proxy_headers
    stored["domain_url"] = req.domain_url.rstrip("/")
    stored["proxy_type"] = req.proxy_type
    if req.tunnel_token:
        stored["tunnel_token"] = req.tunnel_token
    write_json(_HOSTING_SETTINGS_PATH, stored)
    return {
        "cookie_secure": stored["cookie_secure"],
        "trust_proxy_headers": stored["trust_proxy_headers"],
        "domain_url": stored["domain_url"],
        "proxy_type": stored["proxy_type"],
        "tunnel_token_set": bool(stored.get("tunnel_token", "")),
    }


@router.post("/admin/hosting-settings/apply")
def apply_hosting_settings(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    stored = read_json(_HOSTING_SETTINGS_PATH, default={})
    if stored.get("proxy_type") != "cloudflare":
        raise HTTPException(
            status_code=400, detail="Apply is only available for Cloudflare Tunnel mode."
        )
    token = stored.get("tunnel_token", "")
    if not token:
        raise HTTPException(status_code=400, detail="No tunnel token saved. Save settings first.")
    try:
        import docker as docker_sdk

        client = docker_sdk.from_env()
        # Stop and remove the existing container so we can recreate it with the current token.
        # A plain restart keeps the original env vars from container creation time.
        try:
            old = client.containers.get("logcore-tunnel")
            old.stop(timeout=10)
            old.remove()
        except docker_sdk.errors.NotFound:
            pass
        client.containers.run(
            "cloudflare/cloudflared:latest",
            command="tunnel --no-autoupdate run",
            name="logcore-tunnel",
            detach=True,
            network_mode="host",
            restart_policy={"Name": "unless-stopped"},
            environment={"TUNNEL_TOKEN": token},
        )
    except docker_sdk.errors.DockerException as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Admin — registration settings
# ---------------------------------------------------------------------------


class AdminSettingsRequest(BaseModel):
    allow_open_registration: bool | None = None
    enabled_workspaces: list[str] | None = None
    session_minutes: int | None = Field(default=None, ge=60, le=129600)
    require_2fa: Literal["off", "admin", "all"] | None = None

    @field_validator("enabled_workspaces")
    @classmethod
    def _validate_workspaces(cls, v):
        if v is None:
            return v
        invalid = [w for w in v if w not in _VALID_WORKSPACES]
        if invalid:
            raise ValueError(f"Invalid workspace(s): {invalid}")
        if not v:
            raise ValueError("At least one workspace must remain enabled")
        return v


@router.get("/admin/settings")
def get_admin_settings(current_user: dict = Depends(require_admin)):
    runtime = auth_service.get_system_settings()
    return {
        "allow_open_registration": runtime.get(
            "allow_open_registration", settings.allow_open_registration
        ),
        "enabled_workspaces": auth_service.enabled_workspaces(),
        "session_minutes": auth_service.get_effective_session_minutes(),
        "require_2fa": runtime.get("require_2fa", "off"),
    }


@router.patch("/admin/settings")
def update_admin_settings(
    req: AdminSettingsRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    # Don't let the person flipping the switch lock themselves out — mirrors
    # the last-admin-lockout guards' 409 style, but this is "you personally
    # need 2FA before requiring it of others," not an admin-scarcity check.
    if req.require_2fa and req.require_2fa != "off" and not current_user.get("totp_enabled"):
        raise HTTPException(
            status_code=409,
            detail="Enable two-factor authentication on your own account before requiring it for others.",
        )
    updated = auth_service.update_system_settings(req.model_dump(exclude_none=True))
    return {
        "allow_open_registration": updated.get("allow_open_registration"),
        "enabled_workspaces": auth_service.enabled_workspaces(),
        "session_minutes": auth_service.get_effective_session_minutes(),
        "require_2fa": updated.get("require_2fa", "off"),
    }
