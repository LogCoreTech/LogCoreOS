"""Admin user management — create/list/update-role/delete/deletion-preview/
deletion-execute/workspaces/pool-edit/workspace-modules endpoints, split out
of the old routers/auth.py. See routers/auth/__init__.py's docstring for the
full rationale of this package split."""

import logging
import shutil
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator

from services import auth_service, user_deletion_service
from services.features_service import all_module_ids as _all_module_ids
from services.file_service import user_path

from .deps import _admin_limit, _validate_timezone, _VALID_WORKSPACES, require_admin

router = APIRouter()

logger = logging.getLogger("logcore.auth")


@router.get("/users")
def list_users_legacy(current_user: dict = Depends(require_admin)):
    """List all users without sensitive fields (admin only)."""
    data = auth_service._load_auth()
    safe_fields = {"id", "name", "email", "role", "timezone", "disabled_modules", "created_at"}
    return [{k: v for k, v in u.items() if k in safe_fields} for u in data["users"]]


class RoleUpdateRequest(BaseModel):
    role: Literal["admin", "member"]


@router.patch("/users/{user_id}/role")
def update_user_role_legacy(
    user_id: str,
    req: RoleUpdateRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Promote or demote a user's role (admin only)."""
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    user = auth_service.update_user(user_id, {"role": req.role})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "role": req.role}


class ModuleAccessRequest(BaseModel):
    disabled_modules: list[str]

    @field_validator("disabled_modules")
    @classmethod
    def validate_module_ids(cls, v: list[str]) -> list[str]:
        # Computed fresh, not cached at import time — must reflect live
        # install state, same reasoning as all_module_ids() itself.
        invalid = [m for m in v if m not in set(_all_module_ids())]
        if invalid:
            raise ValueError(f"Unknown module IDs: {invalid}")
        return v


@router.patch("/users/{user_id}/modules")
def update_user_modules(
    user_id: str,
    req: ModuleAccessRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Set which modules are disabled for a given user (admin only)."""
    if user_id == current_user["id"]:
        raise HTTPException(
            status_code=400, detail="Admins cannot restrict their own module access"
        )
    user = auth_service.update_user(user_id, {"disabled_modules": req.disabled_modules})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "disabled_modules": req.disabled_modules}


class WorkspacesRequest(BaseModel):
    workspaces: list[str]

    @field_validator("workspaces")
    @classmethod
    def validate_workspaces(cls, v: list[str]) -> list[str]:
        invalid = [w for w in v if w not in _VALID_WORKSPACES]
        if invalid:
            raise ValueError(f"Unknown workspaces: {invalid}")
        if not v:
            raise ValueError("At least one workspace is required")
        return v


@router.patch("/admin/users/{user_id}/workspaces")
def update_user_workspaces(
    user_id: str,
    req: WorkspacesRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Set which workspaces a user can access (admin only)."""
    disabled = [w for w in req.workspaces if w not in auth_service.enabled_workspaces()]
    if disabled:
        raise HTTPException(
            status_code=400,
            detail=f"Workspace(s) disabled for this instance: {disabled}",
        )
    user = auth_service.update_user(user_id, {"workspaces": req.workspaces})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "workspaces": req.workspaces}


_VALID_POOLS = {"household", "team"}


class PoolEditRequest(BaseModel):
    pool_edit: list[str]

    @field_validator("pool_edit")
    @classmethod
    def validate_pools(cls, v: list[str]) -> list[str]:
        invalid = [p for p in v if p not in _VALID_POOLS]
        if invalid:
            raise ValueError(f"Unknown pool(s): {invalid}")
        return sorted(set(v))


@router.patch("/admin/users/{user_id}/pool-edit")
def update_user_pool_edit(
    user_id: str,
    req: PoolEditRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Grant/revoke household & team pool-management rights for a user (admin only)."""
    user = auth_service.update_user(user_id, {"pool_edit": req.pool_edit})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "pool_edit": req.pool_edit}


class WorkspaceModulesRequest(BaseModel):
    workspace: str
    disabled_modules: list[str]

    @field_validator("workspace")
    @classmethod
    def validate_ws(cls, v: str) -> str:
        if v not in _VALID_WORKSPACES:
            raise ValueError(f"workspace must be one of: {_VALID_WORKSPACES}")
        return v

    @field_validator("disabled_modules")
    @classmethod
    def validate_mods(cls, v: list[str]) -> list[str]:
        invalid = [m for m in v if m not in set(_all_module_ids())]
        if invalid:
            raise ValueError(f"Unknown module IDs: {invalid}")
        return v


@router.patch("/admin/users/{user_id}/workspace-modules")
def update_workspace_modules(
    user_id: str,
    req: WorkspaceModulesRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Set disabled modules for a specific workspace for a user (admin only)."""
    if user_id == current_user["id"]:
        raise HTTPException(
            status_code=400, detail="Admins cannot restrict their own module access"
        )
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    raw = target.get("disabled_modules", {})
    if isinstance(raw, list):
        raw = {"personal": raw, "business": raw}
    raw[req.workspace] = req.disabled_modules
    auth_service.update_user(user_id, {"disabled_modules": raw})
    return {"ok": True, "workspace": req.workspace, "disabled_modules": req.disabled_modules}


class UserUpdateRequest(BaseModel):
    timezone: str | None = Field(None, max_length=50)


@router.patch("/users/{user_id}")
def update_user_by_admin(
    user_id: str,
    req: UserUpdateRequest,
    current_user: dict = Depends(require_admin),
):
    """Update user fields that admins control (timezone, etc.)."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "timezone" in updates:
        _validate_timezone(updates["timezone"])
    if not updates:
        return {"ok": True}
    user = auth_service.update_user(user_id, updates)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, **updates}


# ---------------------------------------------------------------------------
# Admin — user management
# ---------------------------------------------------------------------------


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str
    role: Literal["admin", "member", "guest"] = "member"
    feature_role: str = "guest"
    workspaces: list[str] = ["personal"]
    # Link this new account to an EXISTING household-pool contact instead of
    # lazily auto-creating a fresh self-contact on first /contacts/me visit —
    # creation-only, no other entry point retroactively links one (owner item
    # #4). Must not already be self_of someone else ("can't reuse an
    # in-use contact"). See routers/contacts.py's GET /available-for-linking.
    contact_id: str | None = None


class UpdateRoleRequest(BaseModel):
    role: Literal["admin", "member", "guest"]


@router.post("/admin/users", status_code=201)
def admin_create_user(
    req: CreateUserRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    from services import contacts_service

    if req.contact_id:
        # Fail-fast pre-check so a bad contact_id never creates an account at
        # all — the authoritative check (same two conditions, race-safe) runs
        # again inside link_self_contact() itself once the account exists.
        candidate = contacts_service.get_contact(
            contacts_service.POOL_HOUSEHOLD, "personal", req.contact_id
        )
        if candidate is None:
            raise HTTPException(status_code=400, detail="Selected contact not found")
        if candidate.get("self_of"):
            raise HTTPException(
                status_code=400,
                detail=f"That contact is already linked to {candidate['self_of']}'s account",
            )

    try:
        user = auth_service.create_user(req.email, req.password, req.name, role=req.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if req.contact_id:
        try:
            contacts_service.link_self_contact(req.contact_id, user["name"])
        except ValueError:
            # Exceedingly rare race (another admin linked the same contact in
            # the instant between the pre-check above and here) — the account
            # itself was already legitimately created, so don't fail the
            # whole request over it. The new user gets an ordinary
            # freshly-created self-contact on their first /contacts/me visit
            # instead, same as if contact_id had never been provided.
            logger.warning(
                "admin_create_user: link_self_contact race for contact_id=%r, user=%r",
                req.contact_id,
                user["name"],
                exc_info=True,
            )

    updates: dict = {}
    feature_role = (req.feature_role or "").strip().lower()
    if feature_role and feature_role != "guest":
        updates["feature_role"] = feature_role
    valid_ws = [w for w in req.workspaces if w in ("personal", "business")]
    if valid_ws:
        updates["workspaces"] = valid_ws
    if updates:
        auth_service.update_user(user["id"], updates)
    return {k: v for k, v in user.items() if k in {"id", "email", "name", "role", "created_at"}}


_ADMIN_USER_FIELDS = {
    "id",
    "email",
    "name",
    "role",
    "created_at",
    "feature_role",
    "disabled_modules",
    "workspaces",
    "pool_edit",
    "timezone",
}


@router.get("/admin/users")
def admin_list_users(current_user: dict = Depends(require_admin)):
    data = auth_service._load_auth()
    users = [{k: v for k, v in u.items() if k in _ADMIN_USER_FIELDS} for u in data.get("users", [])]
    return {"users": users}


@router.patch("/admin/users/{user_id}")
def admin_update_user_role(
    user_id: str,
    req: UpdateRoleRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    try:
        return auth_service.update_user_role(user_id, req.role)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/admin/users/{user_id}", status_code=204)
def admin_delete_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    preview = user_deletion_service.build_preview(target)
    if preview["eligible_items"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "This user owns items already shared with someone — use "
                "GET/POST .../deletion-preview and .../deletion-execute to resolve them first."
            ),
        )
    auth_service.delete_user(user_id)
    brain_dir = user_path(target["name"])
    if brain_dir.exists():
        shutil.rmtree(brain_dir)


class DeletionDecision(BaseModel):
    module: Literal["assets", "finance", "contacts", "notes"]
    workspace: Literal["personal", "business"]
    item_id: str
    action: Literal["transfer_user", "transfer_pool", "delete"]
    target_user_id: str | None = None


class DeletionExecuteRequest(BaseModel):
    decisions: list[DeletionDecision] = Field(default_factory=list, max_length=500)


@router.get("/admin/users/{user_id}/deletion-preview")
def admin_user_deletion_preview(user_id: str, current_user: dict = Depends(require_admin)):
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    return user_deletion_service.build_preview(target)


@router.post("/admin/users/{user_id}/deletion-execute")
def admin_user_deletion_execute(
    user_id: str,
    req: DeletionExecuteRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        user_deletion_service.execute(
            target,
            [d.model_dump() for d in req.decisions],
            executed_by=current_user["name"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
