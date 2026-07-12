"""Assets module — templates (admin), hierarchical assets, sharing, pools, attachments.

Route order matters: /templates* and /automation* are declared before /{asset_id} so
FastAPI never swallows them as an asset id.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator

from routers.auth import get_workspace, require_admin, require_module
from services import assets_service, automations_config
from services.auth_service import get_user_by_name
from services.rate_limiter import rate_limit

_require_assets = require_module("assets")
_write_limit = rate_limit(30, 60)
_automation_limit = rate_limit(30, 60)

router = APIRouter()


def _validate_asset_id(asset_id: str) -> str:
    try:
        UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset ID format")
    return asset_id


def _find_or_404(current_user: dict, workspace: str, asset_id: str) -> dict:
    found = assets_service.find_asset(
        current_user["name"],
        workspace,
        asset_id,
        is_admin=current_user.get("role") == "admin",
        pool_edit=current_user.get("pool_edit") or [],
        viewer_role=current_user.get("feature_role") or "",
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return found


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class FieldDefModel(BaseModel):
    key: str = Field(..., max_length=40)
    label: str = Field("", max_length=80)
    type: str
    options: list[str] | None = None
    default: object | None = None


class TemplateCreate(BaseModel):
    key: str = Field(..., max_length=40)
    label: str = Field("", max_length=80)
    icon: str = Field("", max_length=8)
    fields: list[FieldDefModel] = Field(default=[], max_length=50)
    owner: str = Field("me", pattern="^(me|global)$")  # global = admin only


class TemplateUpdate(BaseModel):
    label: str | None = Field(None, max_length=80)
    icon: str | None = Field(None, max_length=8)
    fields: list[FieldDefModel] | None = Field(None, max_length=50)
    restrict_roles: list[str] | None = Field(None, max_length=30)


class TemplateShareEntry(BaseModel):
    target: str = Field(..., max_length=100)


class TemplateAccessUpdate(BaseModel):
    shared_with: list[TemplateShareEntry] | None = Field(None, max_length=50)
    restrict_roles: list[str] | None = Field(None, max_length=30)


class ShareRespond(BaseModel):
    notif_id: str = Field(..., max_length=64)
    accept: bool


class AssetCreate(BaseModel):
    template: str | None = Field(None, max_length=40)
    template_id: str | None = Field(None, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: str | None = None
    fields: dict = Field(default={})
    notes: str | None = Field(None, max_length=5000)
    owner: str = Field("me", pattern="^(me|pool)$")


class AssetUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    parent_id: str | None = None
    fields: dict | None = None
    notes: str | None = Field(None, max_length=5000)


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


class ConvertRequest(BaseModel):
    target: str = Field(..., pattern="^pool$")


class AutomationAssetCreate(BaseModel):
    user: str = Field(..., max_length=100)
    workspace: str = Field("personal", pattern="^(personal|business)$")
    template: str = Field(..., max_length=40)
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: str | None = None
    fields: dict = Field(default={})
    notes: str | None = Field(None, max_length=5000)


class AutomationAssetUpdate(BaseModel):
    user: str = Field(..., max_length=100)
    workspace: str = Field("personal", pattern="^(personal|business)$")
    name: str | None = Field(None, max_length=200)
    fields: dict | None = None
    notes: str | None = Field(None, max_length=5000)


class AutomationCommentCreate(BaseModel):
    user: str = Field(..., max_length=100)
    workspace: str = Field("personal", pattern="^(personal|business)$")
    text: str = Field(..., min_length=1, max_length=2000)


# ---------------------------------------------------------------------------
# Templates (global admin-curated + per-user, shareable)
# ---------------------------------------------------------------------------


def _is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


def _template_or_404(tid: str):
    found = assets_service._find_template(tid)
    if found is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return found  # (owner, template)


def _require_template_manage(tid: str, user: dict):
    owner, _ = _template_or_404(tid)
    if owner == assets_service.GLOBAL_OWNER:
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Global templates are admin-managed")
    elif owner != user["name"] and not _is_admin(user):
        raise HTTPException(status_code=403, detail="You can only manage your own templates")
    return owner


@router.get("/templates")
def list_templates(current_user: dict = Depends(_require_assets)):
    return assets_service.visible_templates(
        current_user["name"],
        is_admin=_is_admin(current_user),
        feature_role=current_user.get("feature_role", "member"),
    )


@router.post("/templates", status_code=201)
def create_template(
    req: TemplateCreate,
    current_user: dict = Depends(_require_assets),
    _rl: None = Depends(_write_limit),
):
    is_global = req.owner == "global"
    if is_global and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can create global templates")
    owner = assets_service.GLOBAL_OWNER if is_global else current_user["name"]
    try:
        return assets_service.create_template(req.model_dump(exclude={"owner"}), owner=owner)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/templates/example", status_code=201)
def insert_example_template(
    owner: str = "me",
    current_user: dict = Depends(_require_assets),
    _rl: None = Depends(_write_limit),
):
    if owner == "global" and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can create global templates")
    store_owner = assets_service.GLOBAL_OWNER if owner == "global" else current_user["name"]
    return assets_service.insert_example_template(owner=store_owner)


@router.patch("/templates/{tid}")
def update_template(
    tid: str,
    req: TemplateUpdate,
    current_user: dict = Depends(_require_assets),
    _rl: None = Depends(_write_limit),
):
    _require_template_manage(tid, current_user)
    try:
        result = assets_service.update_template(tid, req.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.delete("/templates/{tid}", status_code=204)
def delete_template(
    tid: str,
    current_user: dict = Depends(_require_assets),
    _rl: None = Depends(_write_limit),
):
    _require_template_manage(tid, current_user)
    try:
        if not assets_service.delete_template(tid):
            raise HTTPException(status_code=404, detail="Template not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.put("/templates/{tid}/access")
def update_template_access(
    tid: str,
    req: TemplateAccessUpdate,
    current_user: dict = Depends(_require_assets),
    _rl: None = Depends(_write_limit),
):
    owner = _require_template_manage(tid, current_user)
    if owner == assets_service.GLOBAL_OWNER:
        # Global templates aren't shared per-user; admins restrict them by role.
        result = assets_service.update_template(tid, {"restrict_roles": req.restrict_roles or []})
        return result or {}
    try:
        result = assets_service.share_template(
            owner, tid, [s.model_dump() for s in (req.shared_with or [])], by=current_user["name"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.post("/templates/{tid}/leave", status_code=204)
def leave_template(
    tid: str,
    current_user: dict = Depends(_require_assets),
    _rl: None = Depends(_write_limit),
):
    found = _template_or_404(tid)
    owner = found[0]
    if owner == assets_service.GLOBAL_OWNER:
        raise HTTPException(status_code=400, detail="Global templates can't be left")
    assets_service.leave_template_share(current_user["name"], owner, tid)


# ---------------------------------------------------------------------------
# Automation API (n8n) — X-Automation-Token auth, no JWT
# ---------------------------------------------------------------------------


def _require_automation_token(x_automation_token: str = Header("")) -> None:
    if not automations_config.verify_api_token(x_automation_token):
        raise HTTPException(status_code=401, detail="Invalid automation token")


def _automation_store(user: str, workspace: str) -> tuple[str, str]:
    """Resolve the target store: a real user, or _team/_household pool names."""
    if user in ("_team", "_household"):
        return user, "personal"
    if get_user_by_name(user) is None:
        raise HTTPException(status_code=404, detail=f"Unknown user {user!r}")
    return user, workspace


@router.get("/automation/token")
def get_automation_token(current_user: dict = Depends(require_admin)):
    return {"token": automations_config.get_api_token()}


@router.post("/automation/token/rotate")
def rotate_automation_token(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    return {"token": automations_config.rotate_api_token()}


@router.get("/automation/assets")
def automation_list_assets(
    user: str,
    workspace: str = "personal",
    template: str | None = None,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    store, store_ws = _automation_store(user, workspace)
    items = assets_service.list_assets(store, store_ws)
    if template:
        items = [a for a in items if a.get("template") == template]
    return items


@router.post("/automation/assets", status_code=201)
def automation_create_asset(
    req: AutomationAssetCreate,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    store, store_ws = _automation_store(req.user, req.workspace)
    try:
        return assets_service.create_asset(
            store,
            req.model_dump(exclude={"user", "workspace"}),
            workspace=store_ws,
            created_by="automation",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/automation/assets/{asset_id}")
def automation_update_asset(
    asset_id: str,
    req: AutomationAssetUpdate,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    _validate_asset_id(asset_id)
    store, store_ws = _automation_store(req.user, req.workspace)
    try:
        result = assets_service.update_asset(
            store,
            asset_id,
            req.model_dump(exclude_unset=True, exclude={"user", "workspace"}),
            workspace=store_ws,
            by="automation",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return result


@router.post("/automation/assets/{asset_id}/comments", status_code=201)
def automation_add_comment(
    asset_id: str,
    req: AutomationCommentCreate,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    """Workflow-posted comment (attributed 'automation'); triggers the same
    edit-level notifications as a user comment — e.g. n8n posting an alert."""
    _validate_asset_id(asset_id)
    store, store_ws = _automation_store(req.user, req.workspace)
    try:
        comment = assets_service.add_comment(
            store,
            asset_id,
            req.text,
            workspace=store_ws,
            by="automation",
            asset_workspace=req.workspace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if comment is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return comment


# ---------------------------------------------------------------------------
# Assets (JWT; module-gated; workspace-scoped)
# ---------------------------------------------------------------------------


@router.get("")
def list_assets(
    template: str | None = None,
    include_archived: bool = False,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
):
    items = assets_service.list_visible(
        current_user["name"],
        workspace,
        include_archived=include_archived,
        is_admin=current_user.get("role") == "admin",
        pool_edit=current_user.get("pool_edit") or [],
        viewer_role=current_user.get("feature_role") or "",
    )
    if template:
        items = [a for a in items if a.get("template") == template]
    return assets_service.attach_templates(items)


@router.post("", status_code=201)
def create_asset(
    req: AssetCreate,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    creator_access, creator_caps = "edit", None
    if req.parent_id:
        # A child is created in its PARENT's store and inherits the parent's
        # audience — so anyone with edit access (or a contribute grant that
        # includes "children") can grow a shared subtree/"group".
        parent = _find_or_404(current_user, workspace, req.parent_id)
        parent_caps = parent.get("can_contribute") or {}
        if not parent["can_edit"] and "children" not in (parent_caps.get("add") or []):
            raise HTTPException(
                status_code=403, detail="Read-only access — cannot add under this asset"
            )
        store, store_ws = parent["store"], parent["store_workspace"]
        if not parent["can_edit"]:
            creator_access, creator_caps = "contribute", parent["can_contribute"]
    elif req.owner == "pool":
        pool_label = assets_service.POOL_LABEL[assets_service.POOL_USERS[workspace]]
        is_admin = current_user.get("role") == "admin"
        if not is_admin and pool_label not in (current_user.get("pool_edit") or []):
            raise HTTPException(
                status_code=403,
                detail="Pool asset creation requires admin or pool management rights",
            )
        store, store_ws = assets_service.POOL_USERS[workspace], "personal"
    else:
        store, store_ws = current_user["name"], workspace
    try:
        created = assets_service.create_asset(
            store,
            req.model_dump(exclude={"owner"}),
            workspace=store_ws,
            created_by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Annotate like list/find responses when the record lives outside the
    # creator's own store. The frontend flips the create modal straight into
    # edit mode on this response and gates pool/share UI on _owner/_access —
    # a bare record made it treat a fresh pool asset as personal and send
    # shared_with on save (400 "use hidden_from instead of shares").
    if store in assets_service.POOL_LABEL:
        out = {**created, "_owner": assets_service.POOL_LABEL[store], "_access": creator_access}
    elif store != current_user["name"]:
        out = {**created, "_owner": store, "_access": creator_access}
    else:
        return created
    if creator_caps is not None:
        out["_caps"] = creator_caps
    return out


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


@router.get("/{asset_id}")
def get_asset(
    asset_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    asset = dict(found["asset"])
    if found["relation"] in ("pool", "shared"):
        asset["_owner"] = (
            assets_service.POOL_LABEL[found["store"]]
            if found["relation"] == "pool"
            else found["store"]
        )
        if found["can_edit"]:
            asset["_access"] = "edit"
        elif found.get("can_contribute"):
            asset["_access"] = "contribute"
            asset["_caps"] = found["can_contribute"]
        else:
            asset["_access"] = "read"
    asset["_template"] = assets_service.resolve_template(asset)
    return asset


@router.patch("/{asset_id}")
def update_asset(
    asset_id: str,
    req: AssetUpdate,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    updates = req.model_dump(exclude_unset=True)
    if not found["can_edit"]:
        # Contribute-level: only the field keys granted in the share/contributor
        # caps may change — never name/parent/notes.
        caps = found.get("can_contribute")
        if not caps:
            raise HTTPException(status_code=403, detail="Read-only access to this asset")
        allowed = set(caps.get("fields") or [])
        blocked = [k for k in updates if k != "fields"]
        bad_fields = [k for k in (updates.get("fields") or {}) if k not in allowed]
        if blocked or bad_fields:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Contribute access can only change these fields: "
                    + (", ".join(sorted(allowed)) or "none")
                ),
            )
    if found["relation"] == "shared" and ("parent_id" in updates):
        raise HTTPException(status_code=403, detail="Only the owner can move this asset")
    try:
        result = assets_service.update_asset(
            found["store"],
            asset_id,
            updates,
            workspace=found["store_workspace"],
            by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return result


@router.post("/{asset_id}/archive")
def archive_asset(
    asset_id: str,
    cascade: bool = False,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    return _set_archived(asset_id, True, current_user, workspace, cascade)


@router.post("/{asset_id}/unarchive")
def unarchive_asset(
    asset_id: str,
    cascade: bool = False,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    return _set_archived(asset_id, False, current_user, workspace, cascade)


def _set_archived(asset_id: str, archived: bool, current_user: dict, workspace: str, cascade: bool):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if not found["can_manage"]:
        raise HTTPException(status_code=403, detail="Only the owner or a pool manager can archive")
    return assets_service.set_archived(
        found["store"],
        asset_id,
        archived,
        workspace=found["store_workspace"],
        by=current_user["name"],
        cascade=cascade,
    )


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


@router.delete("/{asset_id}", status_code=204)
def delete_asset(
    asset_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    # Owners delete their own personal assets; pool assets stay admin-only.
    if not found["can_delete"]:
        raise HTTPException(status_code=403, detail="Only an admin can delete this asset")
    try:
        if not assets_service.delete_asset(
            found["store"], asset_id, workspace=found["store_workspace"]
        ):
            raise HTTPException(status_code=404, detail="Asset not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{asset_id}/convert")
def convert_asset(
    asset_id: str,
    req: ConvertRequest,
    current_user: dict = Depends(require_admin),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if found["relation"] == "pool":
        raise HTTPException(status_code=400, detail="Asset is already a pool asset")
    try:
        return assets_service.convert_to_pool(
            found["store"], asset_id, workspace=found["store_workspace"], by=current_user["name"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    comment = next(
        (c for c in found["asset"].get("comments") or [] if c.get("id") == comment_id), None
    )
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.get("by") != current_user["name"] and not found["can_manage"]:
        raise HTTPException(
            status_code=403, detail="Only the comment author or the owner can delete it"
        )
    assets_service.delete_comment(
        found["store"], asset_id, comment_id, workspace=found["store_workspace"]
    )


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


@router.post("/{asset_id}/files", status_code=201)
async def upload_attachment(
    asset_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    caps = found.get("can_contribute") or {}
    if not found["can_edit"] and "files" not in (caps.get("add") or []):
        raise HTTPException(status_code=403, detail="Read-only access to this asset")
    if (file.content_type or "") not in assets_service.ATTACHMENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type — images or PDF only")
    data = await file.read()
    try:
        return assets_service.add_attachment(
            found["store"],
            asset_id,
            file.filename or "",
            file.content_type or "",
            data,
            workspace=found["store_workspace"],
            by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{asset_id}/files/{file_id}")
def get_attachment(
    asset_id: str,
    file_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
):
    from fastapi.responses import FileResponse

    _validate_asset_id(asset_id)
    _validate_asset_id(file_id)
    found = _find_or_404(current_user, workspace, asset_id)
    meta = assets_service.get_attachment(
        found["store"], asset_id, file_id, workspace=found["store_workspace"]
    )
    if meta is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(meta["path"]), media_type=meta["mime"], filename=meta["filename"])


@router.delete("/{asset_id}/files/{file_id}", status_code=204)
def delete_attachment(
    asset_id: str,
    file_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    _validate_asset_id(file_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if not found["can_edit"]:
        raise HTTPException(status_code=403, detail="Read-only access to this asset")
    if not assets_service.delete_attachment(
        found["store"],
        asset_id,
        file_id,
        workspace=found["store_workspace"],
        by=current_user["name"],
    ):
        raise HTTPException(status_code=404, detail="File not found")
