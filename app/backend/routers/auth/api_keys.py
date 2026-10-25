"""Admin → API Keys: create, list, edit, and revoke API keys
(services/api_key_service.py) — integration keys (a website lead form) and
MCP keys (an AI app, with per-module tool access). Admin-only by owner
decision (docs/MEMORY.md 2026-10-25). Every route here is a cookie/JWT
session route via require_admin, and get_current_user rejects an API key
outright, so a key can never be used to mint or manage other keys."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import api_key_service, audit_log, auth_service, mcp_service
from services.rate_limiter import rate_limit

from .deps import _admin_limit, require_admin

router = APIRouter()

# Creation checks a password — same tier as the other password-confirming
# endpoints (_password_limit in profile.py), not the looser admin-op limit.
_api_key_create_limit = rate_limit(5, 60)
_api_key_read_limit = rate_limit(30, 60)


class ApiKeyCreateRequest(BaseModel):
    kind: Literal["integration", "mcp"]
    name: str = Field(..., min_length=1, max_length=60)
    expires_days: int | None = None
    current_password: str = Field(..., min_length=1)
    # integration only
    target: Literal["_team", "_household"] | None = None
    # mcp only
    workspace: Literal["personal", "business"] = "personal"
    access: dict[str, str] = Field(default_factory=dict)
    tool_overrides: dict[str, bool] = Field(default_factory=dict)


class ApiKeyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    access: dict[str, str] | None = None
    tool_overrides: dict[str, bool] | None = None


@router.get("/admin/api-keys")
def admin_list_api_keys(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_api_key_read_limit),
):
    """Every key on the instance (metadata only — never a secret or hash),
    plus what the create/edit UI needs: the MCP tool catalog and options."""
    return {
        "enabled": api_key_service.keys_enabled(),
        "expiry_days": list(api_key_service.EXPIRY_DAYS),
        "workspaces": auth_service.enabled_workspaces(),
        "mcp_catalog": mcp_service.catalog(),
        "keys": api_key_service.list_keys(),
    }


@router.post("/admin/api-keys")
def admin_create_api_key(
    req: ApiKeyCreateRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_api_key_create_limit),
):
    """Create a key. An integration key belongs to the instance; an MCP key
    belongs to YOU (the caller). The full key is in this response only."""
    if not api_key_service.keys_enabled():
        raise HTTPException(status_code=409, detail="API keys are turned off")
    if not auth_service.verify_password(req.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        meta, full_key = api_key_service.create_key(
            current_user,
            req.kind,
            req.name,
            req.expires_days,
            target=req.target,
            workspace=req.workspace,
            access=req.access,
            tool_overrides=req.tool_overrides,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_log.record(current_user, "api_key.create", meta["name"], _audit_details(meta))
    return {"key": full_key, "meta": meta}


@router.patch("/admin/api-keys/{key_id}")
def admin_update_api_key(
    key_id: str,
    req: ApiKeyUpdateRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Rename a key, or change an MCP key's tool access. Takes effect on the
    key's next request; the key itself (the secret) doesn't change."""
    try:
        meta = api_key_service.update_key(
            key_id, name=req.name, access=req.access, tool_overrides=req.tool_overrides
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if meta is None:
        raise HTTPException(status_code=404, detail="API key not found")
    audit_log.record(current_user, "api_key.update", meta["name"], _audit_details(meta))
    return {"ok": True, "meta": meta}


@router.delete("/admin/api-keys/{key_id}")
def admin_revoke_api_key(
    key_id: str,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Revoke any key (an admin can revoke another admin's MCP key — e.g. one
    that leaked while its owner is away). Takes effect on the next request."""
    meta = api_key_service.revoke_key(key_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="API key not found")
    audit_log.record(current_user, "api_key.revoke", meta["name"], _audit_details(meta))
    return {"ok": True, "meta": meta}


def _audit_details(meta: dict) -> dict:
    details = {"key_id": meta["id"], "kind": meta["kind"], "workspace": meta["workspace"]}
    if meta["kind"] == api_key_service.KIND_INTEGRATION:
        details["target"] = meta["target"]
    else:
        details.update(
            {
                "owner": meta.get("user_name", ""),
                "access": meta.get("access", {}),
                "tool_overrides": meta.get("tool_overrides", {}),
            }
        )
    return details
