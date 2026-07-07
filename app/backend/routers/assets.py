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


class TemplateUpdate(BaseModel):
    label: str | None = Field(None, max_length=80)
    icon: str | None = Field(None, max_length=8)
    fields: list[FieldDefModel] | None = Field(None, max_length=50)


class AssetCreate(BaseModel):
    template: str = Field(..., max_length=40)
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


class ShareEntry(BaseModel):
    target: str = Field(..., max_length=100)
    access: str = Field("read", pattern="^(read|edit)$")


class AccessUpdate(BaseModel):
    shared_with: list[ShareEntry] | None = Field(None, max_length=50)
    hidden_from: list[str] | None = Field(None, max_length=50)

    @field_validator("hidden_from")
    @classmethod
    def _names_max_len(cls, v):
        if v is not None and any(len(n) > 100 for n in v):
            raise ValueError("User name too long")
        return v


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


# ---------------------------------------------------------------------------
# Templates (admin-curated; readable by all module users)
# ---------------------------------------------------------------------------


@router.get("/templates")
def list_templates(current_user: dict = Depends(_require_assets)):
    return assets_service.list_templates()


@router.post("/templates", status_code=201)
def create_template(
    req: TemplateCreate,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    try:
        return assets_service.create_template(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/templates/example", status_code=201)
def insert_example_template(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    return assets_service.insert_example_template()


@router.patch("/templates/{key}")
def update_template(
    key: str,
    req: TemplateUpdate,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    try:
        result = assets_service.update_template(key, req.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.delete("/templates/{key}", status_code=204)
def delete_template(
    key: str,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    try:
        if not assets_service.delete_template(key):
            raise HTTPException(status_code=404, detail="Template not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


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
    )
    if template:
        items = [a for a in items if a.get("template") == template]
    return items


@router.post("", status_code=201)
def create_asset(
    req: AssetCreate,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    if req.owner == "pool":
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
        return assets_service.create_asset(
            store,
            req.model_dump(exclude={"owner"}),
            workspace=store_ws,
            created_by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{asset_id}")
def get_asset(
    asset_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    asset = dict(found["asset"])
    if found["relation"] == "pool":
        asset["_owner"] = assets_service.POOL_LABEL[found["store"]]
        asset["_access"] = "edit" if found["can_edit"] else "read"
    elif found["relation"] == "shared":
        asset["_owner"] = found["store"]
        asset["_access"] = "edit" if found["can_edit"] else "read"
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
    if not found["can_edit"]:
        raise HTTPException(status_code=403, detail="Read-only access to this asset")
    updates = req.model_dump(exclude_unset=True)
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
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    return _set_archived(asset_id, True, current_user, workspace)


@router.post("/{asset_id}/unarchive")
def unarchive_asset(
    asset_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    return _set_archived(asset_id, False, current_user, workspace)


def _set_archived(asset_id: str, archived: bool, current_user: dict, workspace: str):
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
    )


@router.delete("/{asset_id}", status_code=204)
def delete_asset(
    asset_id: str,
    current_user: dict = Depends(require_admin),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
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
    try:
        result = assets_service.update_access(
            found["store"],
            asset_id,
            workspace=found["store_workspace"],
            shared_with=[s.model_dump() for s in shared] if shared is not None else None,
            hidden_from=req.hidden_from,
            by=current_user["name"],
            asset_workspace=workspace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return result


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
    if not found["can_edit"]:
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
