"""Admin → API Keys: create, list, and revoke personal API keys
(services/api_key_service.py). Admin-only by owner decision (docs/MEMORY.md
2026-10-25) — every route here is a cookie/JWT session route via
require_admin, and get_current_user rejects an API key outright, so a key can
never be used to mint or manage other keys."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import api_key_service, audit_log, auth_service
from services.rate_limiter import rate_limit

from .deps import _admin_limit, require_admin

router = APIRouter()

# Creation checks a password — same tier as the other password-confirming
# endpoints (_password_limit in profile.py), not the looser admin-op limit.
_api_key_create_limit = rate_limit(5, 60)
_api_key_read_limit = rate_limit(30, 60)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    scopes: list[str] = Field(..., min_length=1, max_length=len(api_key_service.SCOPES))
    workspace: str = "personal"
    expires_days: int | None = None
    current_password: str = Field(..., min_length=1)


@router.get("/admin/api-keys")
def admin_list_api_keys(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_api_key_read_limit),
):
    """Every key on the instance (metadata only — never a secret or hash)."""
    return {
        "enabled": api_key_service.keys_enabled(),
        "scopes": api_key_service.SCOPES,
        "expiry_days": list(api_key_service.EXPIRY_DAYS),
        "keys": api_key_service.list_keys(),
    }


@router.post("/admin/api-keys")
def admin_create_api_key(
    req: ApiKeyCreateRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_api_key_create_limit),
):
    """Create a key for YOUR OWN account. The full key is in this response
    only — it can't be shown again."""
    if not api_key_service.keys_enabled():
        raise HTTPException(status_code=409, detail="API keys are turned off in Admin → General")
    if not auth_service.verify_password(req.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        meta, full_key = api_key_service.create_key(
            current_user, req.name, req.scopes, req.workspace, req.expires_days
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_log.record(
        current_user,
        "api_key.create",
        meta["name"],
        {"key_id": meta["id"], "scopes": meta["scopes"], "workspace": meta["workspace"]},
    )
    return {"key": full_key, "meta": meta}


@router.delete("/admin/api-keys/{key_id}")
def admin_revoke_api_key(
    key_id: str,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Revoke any key (an admin can revoke another admin's key — e.g. one
    that leaked while its owner is away). Takes effect on the next request."""
    meta = api_key_service.revoke_key(key_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="API key not found")
    audit_log.record(
        current_user,
        "api_key.revoke",
        meta["name"],
        {"key_id": key_id, "owner": meta.get("user_name", "")},
    )
    return {"ok": True, "meta": meta}
