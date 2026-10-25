"""Integrations & MCP keys (services/api_key_service.py; docs/MEMORY.md
2026-10-25).

Admin side (`/admin/api-keys…`, require_admin): create integration keys
(the admin gets the key once), invite a chosen user to an MCP key with
picked tools (the admin never gets that key), edit, revoke, and handle
users' access requests.

User side (`/me/api-keys…`, any logged-in user): see the MCP keys that act
as you, accept (password-confirmed — the key is generated and shown once,
right then) or decline an invite, approve or reject a widening of an
accepted key's tools, revoke your own key, and request access.

Every route is a cookie/JWT session route, and get_current_user rejects an
API key outright, so a key can never be used to mint or manage keys."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import api_key_service, audit_log, auth_service, mcp_service
from services.features_service import get_effective_disabled
from services.intake_spec import intake_spec
from services.rate_limiter import rate_limit

from .deps import _admin_limit, get_current_user, require_admin

router = APIRouter()

# Creating/accepting a key checks a password — same tier as the other
# password-confirming endpoints (_password_limit in profile.py).
_api_key_password_limit = rate_limit(5, 60)
_api_key_read_limit = rate_limit(30, 60)
_api_key_write_limit = rate_limit(10, 60)
_api_key_request_limit = rate_limit(3, 3600)


class McpGrant(BaseModel):
    access: dict[str, str] = Field(default_factory=dict)
    tool_overrides: dict[str, bool] = Field(default_factory=dict)


class ApiKeyCreateRequest(BaseModel):
    kind: Literal["integration", "mcp"]
    name: str = Field(..., min_length=1, max_length=60)
    expires_days: int | None = None
    current_password: str = Field(..., min_length=1)
    # integration only
    target: Literal["_team", "_household"] | None = None
    # mcp only — the admin chooses who the key acts as and, per workspace,
    # what it can use: {"business": {"access": {...}, "tool_overrides": {...}}}
    user_id: str | None = None
    grants: dict[Literal["personal", "business"], McpGrant] = Field(default_factory=dict)


class ApiKeyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    grants: dict[Literal["personal", "business"], McpGrant] | None = None


def _grants_dict(grants) -> dict | None:
    return None if grants is None else {w: g.model_dump() for w, g in grants.items()}


class ApiKeyAcceptRequest(BaseModel):
    current_password: str = Field(..., min_length=1)


class ApiKeyChangeResponse(BaseModel):
    accept: bool


class ApiKeyAccessRequest(BaseModel):
    note: str = Field(default="", max_length=500)


def _require_enabled() -> None:
    if not api_key_service.keys_enabled():
        raise HTTPException(status_code=409, detail="Integrations & MCP keys are turned off")


def _notify(user_name: str, title: str, body: str, action: dict, url: str) -> None:
    from services.suggestions_service import notify_user

    try:
        notify_user(user_name, title, body, source="api_keys", action=action, url=url)
    except Exception:  # a notification must never break the write path
        pass


def _invite_notice(meta: dict, admin_name: str, change: bool = False) -> None:
    title = "Review a change to your MCP access" if change else "MCP access set up for you"
    body = (
        f"{admin_name} wants to give “{meta['name']}” more tools. Review it in Settings → Account."
        if change
        else f"{admin_name} set up an MCP key, “{meta['name']}”, that lets an AI app act as you. "
        "Review and accept it in Settings → Account."
    )
    _notify(
        meta["user_name"],
        title,
        body,
        {"type": "open_mcp_access", "key_id": meta["id"]},
        f"/settings/account?mcp={meta['id']}",
    )


def _audit_details(meta: dict) -> dict:
    details = {"key_id": meta["id"], "kind": meta["kind"]}
    if meta["kind"] == api_key_service.KIND_INTEGRATION:
        details.update({"target": meta["target"], "workspace": meta["workspace"]})
    else:
        details.update(
            {"user": meta.get("user_name", ""), "grants": api_key_service.grants_of(meta)}
        )
    return details


def _with_tools(meta: dict) -> dict:
    """An MCP key plus exactly which tools it grants (and would grant, if a
    widening is waiting for approval) — what the user reviews before saying yes."""
    out = dict(meta)
    if meta["kind"] == api_key_service.KIND_MCP:
        out["grants"] = api_key_service.grants_of(meta)
        out["granted_tools"] = mcp_service.granted_tools(out["grants"])
        if meta.get("proposed_grants") is not None:
            out["proposed_tools"] = mcp_service.granted_tools(meta["proposed_grants"])
    return out


# --- admin ------------------------------------------------------------------------


@router.get("/admin/api-keys")
def admin_list_api_keys(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_api_key_read_limit),
):
    """Every key on the instance (metadata only — never a secret or hash),
    open access requests, and what the create/edit UI needs."""
    users = []
    for u in auth_service.list_users():
        full = auth_service.get_user_by_id(u["id"])
        if full:
            workspaces = api_key_service.usable_workspaces(full)
            users.append(
                {
                    "id": full["id"],
                    "name": full["name"],
                    "role": full.get("role", "member"),
                    "workspaces": workspaces,
                    # what the picker may offer per workspace: their own modules
                    "disabled_modules": {
                        w: get_effective_disabled(
                            full.get("feature_role", "member"), full.get("disabled_modules", []), w
                        )
                        for w in workspaces
                    },
                }
            )
    return {
        "enabled": api_key_service.keys_enabled(),
        "expiry_days": list(api_key_service.EXPIRY_DAYS),
        "workspaces": auth_service.enabled_workspaces(),
        "users": users,
        "mcp_catalog": mcp_service.catalog(),
        "requests": api_key_service.list_requests(),
        "keys": [_with_tools(k) for k in api_key_service.list_keys()],
        "intake_spec": intake_spec(),
    }


@router.post("/admin/api-keys")
def admin_create_api_key(
    req: ApiKeyCreateRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_api_key_password_limit),
):
    """integration → `{key, meta}`, the key shown to the admin this once.
    mcp → `{key: null, meta}`: a pending invite; the chosen user is notified
    and only they ever see the key, when they accept it."""
    _require_enabled()
    if not auth_service.verify_password(req.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        if req.kind == api_key_service.KIND_INTEGRATION:
            meta, full_key = api_key_service.create_integration_key(
                current_user, req.name, req.target, req.expires_days
            )
            audit_log.record(current_user, "api_key.create", meta["name"], _audit_details(meta))
            return {"key": full_key, "meta": meta}
        for_user = auth_service.get_user_by_id(req.user_id or "")
        if not for_user:
            raise ValueError("Pick the user this MCP key will act as")
        meta = api_key_service.invite_mcp_key(
            current_user, for_user, req.name, _grants_dict(req.grants), req.expires_days
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_log.record(current_user, "api_key.invite", meta["name"], _audit_details(meta))
    _invite_notice(meta, current_user.get("name", "An admin"))
    return {"key": None, "meta": meta}


@router.patch("/admin/api-keys/{key_id}")
def admin_update_api_key(
    key_id: str,
    req: ApiKeyUpdateRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Rename a key, or change an MCP key's tools. Narrowing applies on the
    key's next request; widening an accepted key waits for its user to
    approve (`needs_approval: true`) — until then the old tools stand."""
    try:
        result = api_key_service.update_key(key_id, name=req.name, grants=_grants_dict(req.grants))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="API key not found")
    meta, needs_approval = result
    action = "api_key.change_proposed" if needs_approval else "api_key.update"
    audit_log.record(current_user, action, meta["name"], _audit_details(meta))
    if needs_approval:
        _invite_notice(meta, current_user.get("name", "An admin"), change=True)
    return {"ok": True, "meta": meta, "needs_approval": needs_approval}


@router.delete("/admin/api-keys/{key_id}")
def admin_revoke_api_key(
    key_id: str,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Revoke any key or pending invite. Takes effect on the next request."""
    meta = api_key_service.revoke_key(key_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="API key not found")
    audit_log.record(current_user, "api_key.revoke", meta["name"], _audit_details(meta))
    return {"ok": True, "meta": meta}


@router.post("/admin/api-keys/requests/{request_id}/dismiss")
def admin_dismiss_key_request(
    request_id: str,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    request = api_key_service.dismiss_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    audit_log.record(current_user, "api_key.request_dismiss", request["user_name"], {})
    return {"ok": True}


# --- the user's own MCP keys -----------------------------------------------------------


@router.get("/me/api-keys")
def my_api_keys(
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_api_key_read_limit),
):
    """The MCP keys that act as you — each with exactly which tools it grants."""
    return {
        "enabled": api_key_service.keys_enabled(),
        "has_open_request": api_key_service.has_open_request(current_user["id"]),
        "keys": [_with_tools(k) for k in api_key_service.list_user_keys(current_user["id"])],
    }


@router.post("/me/api-keys/{key_id}/accept")
def accept_my_api_key(
    key_id: str,
    req: ApiKeyAcceptRequest,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_api_key_password_limit),
):
    """Accept an invite: the key is generated now and is in this response
    only. Copy it — it can't be shown again."""
    _require_enabled()
    if not auth_service.verify_password(req.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        meta, full_key = api_key_service.accept_invite(key_id, current_user)
    except LookupError:
        raise HTTPException(status_code=404, detail="API key not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    audit_log.record(current_user, "api_key.accept", meta["name"], _audit_details(meta))
    return {"key": full_key, "meta": _with_tools(meta)}


@router.post("/me/api-keys/{key_id}/decline")
def decline_my_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_api_key_write_limit),
):
    try:
        meta = api_key_service.decline_invite(key_id, current_user)
    except LookupError:
        raise HTTPException(status_code=404, detail="API key not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    audit_log.record(current_user, "api_key.decline", meta["name"], _audit_details(meta))
    return {"ok": True}


@router.post("/me/api-keys/{key_id}/change")
def respond_my_api_key_change(
    key_id: str,
    req: ApiKeyChangeResponse,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_api_key_write_limit),
):
    """Approve or reject an admin's proposed widening of this key's tools."""
    try:
        meta = api_key_service.respond_to_change(key_id, current_user, req.accept)
    except LookupError:
        raise HTTPException(status_code=404, detail="API key not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    action = "api_key.change_accept" if req.accept else "api_key.change_decline"
    audit_log.record(current_user, action, meta["name"], _audit_details(meta))
    return {"ok": True, "meta": _with_tools(meta)}


@router.delete("/me/api-keys/{key_id}")
def revoke_my_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_api_key_write_limit),
):
    """Revoke a key that acts as you. You can't create or change one."""
    meta = api_key_service.revoke_key(key_id, user_id=current_user["id"])
    if meta is None:
        raise HTTPException(status_code=404, detail="API key not found")
    audit_log.record(current_user, "api_key.revoke", meta["name"], _audit_details(meta))
    return {"ok": True}


@router.post("/me/api-keys/request")
def request_mcp_access(
    req: ApiKeyAccessRequest,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_api_key_request_limit),
):
    """Ask the admins for MCP access. Every admin is notified."""
    _require_enabled()
    try:
        request = api_key_service.create_request(current_user, req.note)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    audit_log.record(current_user, "api_key.request", current_user["name"], {})
    body = f"{current_user['name']} is asking for MCP access (an AI app acting as them)."
    if request["note"]:
        body += f" Note: “{request['note']}”"
    for admin in auth_service.list_users():
        if admin.get("role") == "admin":
            _notify(
                admin["name"],
                "MCP access requested",
                body,
                {"type": "open_admin_integrations"},
                "/settings/admin/integrations",
            )
    return {"ok": True}
