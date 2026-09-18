"""Assets module: access control, share handshake, comments, and mute state.

Personal-asset shares are per-user REQUESTS (accept/decline via the bell,
resolved through /shares/respond); pool assets take contributor grants
instead (already workspace-visible, no handshake) — same shape as Finance's
own router_sharing.py. Split out of module_packages/assets/backend/router.py
— see that file's docstring for the full split rationale and why route
order matters. GET `/members`/`/roles` and POST `/shares/respond` are static
paths that must be registered before the core module's bare `/{asset_id}`
routes so FastAPI never swallows them as an asset id; `_get_router()` in
manifest.py handles that.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from module_packages.assets.backend.router import _find_or_404, _is_admin, _validate_asset_id
from routers.auth import get_workspace, require_module
from services import assets_service
from services.rate_limiter import rate_limit

_require_assets = require_module("assets")
_write_limit = rate_limit(30, 60)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ShareRespond(BaseModel):
    notif_id: str = Field(..., max_length=64)
    accept: bool


class ContributeCaps(BaseModel):
    fields: list[str] = Field(default=[], max_length=50)
    add: list[str] = Field(default=[], max_length=10)


class ShareEntry(BaseModel):
    target: str = Field(..., max_length=100)
    access: str = Field("read", pattern="^(read|contribute|edit)$")
    caps: ContributeCaps | None = None  # only meaningful for access == "contribute"


class ContributorEntry(BaseModel):
    target: str = Field(..., max_length=100)
    caps: ContributeCaps | None = None


class AccessUpdate(BaseModel):
    shared_with: list[ShareEntry] | None = Field(None, max_length=50)
    hidden_from: list[str] | None = Field(None, max_length=50)
    contributors: list[ContributorEntry] | None = Field(None, max_length=50)  # pool assets only
    cascade: bool = True  # apply to the whole subtree by default

    @field_validator("hidden_from")
    @classmethod
    def _names_max_len(cls, v):
        if v is not None and any(len(n) > 110 for n in v):
            raise ValueError("User name too long")
        return v


class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class CommentsVisibility(BaseModel):
    hidden: bool


class MuteUpdate(BaseModel):
    muted: bool


# ---------------------------------------------------------------------------
# Pickers + share handshake
# ---------------------------------------------------------------------------


@router.get("/members")
def list_members(current_user: dict = Depends(_require_assets)):
    """Member display names for the share/hide selectors. Names only.

    Exposed to any Assets user so they can pick who to share with. May become
    permissioned/opt-in later (see MEMORY.md).
    """
    from services.auth_service import list_users

    return [{"name": u["name"]} for u in list_users()]


@router.get("/roles")
def list_roles(current_user: dict = Depends(_require_assets)):
    """Feature-role names for the share-by-role picker."""
    from services.features_service import load_features

    return sorted((load_features().get("roles") or {}).keys())


@router.post("/shares/respond")
def respond_share(
    req: ShareRespond,
    current_user: dict = Depends(_require_assets),
    _rl: None = Depends(_write_limit),
):
    """Accept/decline a share request delivered as an actionable notification."""
    from services import suggestions_service

    notif = suggestions_service.resolve_notification(current_user["name"], req.notif_id)
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    action = notif.get("action") or {}
    viewer = current_user["name"]
    if action.get("type") == "asset_share":
        assets_service.respond_to_asset_share(viewer, action, req.accept)
    elif action.get("type") == "template_share":
        assets_service.respond_to_template_share(viewer, action, req.accept)
    return {"ok": True}


@router.post("/{asset_id}/leave", status_code=204)
def leave_asset(
    asset_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """A share recipient removes themselves from an asset shared with them."""
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if found["relation"] != "shared":
        raise HTTPException(status_code=400, detail="You can only leave assets shared with you")
    assets_service.leave_asset_share(
        current_user["name"], found["store"], asset_id, found["store_workspace"]
    )


@router.put("/{asset_id}/access")
def update_access(
    asset_id: str,
    req: AccessUpdate,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if not found["can_manage"]:
        raise HTTPException(
            status_code=403, detail="Only the owner or a pool manager can change access"
        )
    shared = req.shared_with
    if found["relation"] == "pool" and shared is not None:
        raise HTTPException(
            status_code=400,
            detail="Pool assets are workspace-visible — use hidden_from instead of shares",
        )
    if found["relation"] != "pool" and req.contributors is not None:
        raise HTTPException(
            status_code=400,
            detail="Contributors are for pool assets — use shared_with with 'contribute' access",
        )
    try:
        result = assets_service.update_access(
            found["store"],
            asset_id,
            workspace=found["store_workspace"],
            shared_with=(
                [s.model_dump(exclude_none=True) for s in shared] if shared is not None else None
            ),
            hidden_from=req.hidden_from,
            contributors=(
                [c.model_dump(exclude_none=True) for c in req.contributors]
                if req.contributors is not None
                else None
            ),
            by=current_user["name"],
            asset_workspace=workspace,
            cascade=req.cascade,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return result


# ---------------------------------------------------------------------------
# Comments — append-only attributed log ("leave notes" without clobbering)
# ---------------------------------------------------------------------------


def _can_comment(found: dict) -> bool:
    """Edit-level users always; contribute users need the 'comments' cap.
    Plain read access is view-only."""
    if found["can_edit"] or found["can_manage"]:
        return True
    caps = found.get("can_contribute") or {}
    return "comments" in (caps.get("add") or [])


@router.post("/{asset_id}/comments", status_code=201)
def add_comment(
    asset_id: str,
    req: CommentCreate,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if not _can_comment(found):
        raise HTTPException(status_code=403, detail="You don't have comment access on this asset")
    try:
        comment = assets_service.add_comment(
            found["store"],
            asset_id,
            req.text,
            workspace=found["store_workspace"],
            by=current_user["name"],
            asset_workspace=workspace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if comment is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return comment


@router.delete("/{asset_id}/comments/{comment_id}", status_code=204)
def delete_comment(
    asset_id: str,
    comment_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """Comments are an audit-style log — only an admin can remove one. Owners
    who want them gone from view use the hide-comments toggle instead."""
    _validate_asset_id(asset_id)
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only an admin can delete comments")
    found = _find_or_404(current_user, workspace, asset_id)
    if not assets_service.delete_comment(
        found["store"], asset_id, comment_id, workspace=found["store_workspace"]
    ):
        raise HTTPException(status_code=404, detail="Comment not found")


@router.put("/{asset_id}/comments/visibility")
def set_comments_visibility(
    asset_id: str,
    req: CommentsVisibility,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """Edit-level toggle (set from the edit page): turn comments off (or back
    on) for ALL users on this asset. Data is kept; posting is blocked while off."""
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if not found["can_edit"]:
        raise HTTPException(status_code=403, detail="Only an edit-level user can change this")
    result = assets_service.set_comments_hidden(
        found["store"],
        asset_id,
        req.hidden,
        workspace=found["store_workspace"],
        by=current_user["name"],
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"ok": True, "comments_hidden": bool(req.hidden)}


@router.get("/{asset_id}/mute")
def get_comment_mute(
    asset_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
):
    """Viewer's own comment-notification state for this asset (+subtree)."""
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    return assets_service.comment_mute_state(
        current_user["name"], found["store"], asset_id, workspace=found["store_workspace"]
    )


@router.put("/{asset_id}/mute")
def set_comment_mute(
    asset_id: str,
    req: MuteUpdate,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """Per-user opt in/out of comment notifications for this asset and
    everything inside it (mute is stored on this node; delivery walks ancestors)."""
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    assets_service.set_comment_mute(current_user["name"], asset_id, req.muted)
    return assets_service.comment_mute_state(
        current_user["name"], found["store"], asset_id, workspace=found["store_workspace"]
    )
