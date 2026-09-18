"""Assets module: template CRUD (admin-curated global + per-user, shareable).

Split out of module_packages/assets/backend/router.py — see that file's
docstring for the full split rationale and why route order matters.
GET/POST `/templates*` are static paths that must be registered before the
core module's bare `/{asset_id}` routes so FastAPI never swallows
"/templates" as an asset id; `_get_router()` in manifest.py handles that.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from module_packages.assets.backend.router import FieldDefModel, _is_admin
from routers.auth import require_module
from services import assets_service
from services.assets_templates_service import _find_template
from services.rate_limiter import rate_limit

_require_assets = require_module("assets")
_write_limit = rate_limit(30, 60)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Templates (global admin-curated + per-user, shareable)
# ---------------------------------------------------------------------------


def _template_or_404(tid: str):
    found = _find_template(tid)
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
