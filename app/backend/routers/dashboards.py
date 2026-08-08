"""Dashboards module — standalone, unlimited, user-created custom dashboards.
Reads/writes route through dashboards_service access resolution so shared and
pool (household/team) dashboards are reachable server-side. Reuses the
existing `dashboard` module id — no new require_module registry entry."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_workspace, require_module
from services import assets_service, contacts_service, dashboard_index, dashboard_templates_service, dashboards_service
from services.dashboard_blocks.registry import catalog
from services.dashboard_blocks.render import render_dashboard
from services.rate_limiter import rate_limit

_require_dashboards = require_module("dashboard")
_read_limit = rate_limit(60, 60)
_write_limit = rate_limit(30, 60)

router = APIRouter()

_ACCESS_ORDER = {"read": 0, "contribute": 1, "edit": 2}


class DashboardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    icon: str = Field(default="📊", max_length=8)
    pool: bool = False
    template_id: str | None = Field(default=None, max_length=64)
    subject_id: str | None = Field(default=None, max_length=64)


class TemplateBlockIn(BaseModel):
    id: str | None = None
    type: str
    config: dict = Field(default_factory=dict)


class TemplateCreate(BaseModel):
    label: str = Field("", max_length=80)
    icon: str = Field("", max_length=8)
    subject_type: str | None = Field(default=None, pattern="^(contact|asset)$")
    blocks: list[TemplateBlockIn] = Field(default=[], max_length=50)
    owner: str = Field("me", pattern="^(me|global)$")  # global = admin only


class TemplateUpdate(BaseModel):
    label: str | None = Field(None, max_length=80)
    icon: str | None = Field(None, max_length=8)
    subject_type: str | None = Field(default=None, pattern="^(contact|asset)$")
    blocks: list[TemplateBlockIn] | None = Field(None, max_length=50)
    restrict_roles: list[str] | None = Field(None, max_length=30)


class TemplateShareEntry(BaseModel):
    target: str = Field(..., max_length=100)


class TemplateAccessUpdate(BaseModel):
    shared_with: list[TemplateShareEntry] | None = Field(None, max_length=50)
    restrict_roles: list[str] | None = Field(None, max_length=30)


class TemplateShareRespond(BaseModel):
    owner: str = Field(..., max_length=100)
    template_id: str = Field(..., max_length=64)
    accept: bool


class SubjectUpdate(BaseModel):
    subject_id: str | None = Field(default=None, max_length=64)


class BlockIn(BaseModel):
    id: str | None = None
    type: str
    config: dict = Field(default_factory=dict)
    layout: dict = Field(default_factory=dict)


class DashboardUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    icon: str | None = Field(default=None, max_length=8)
    blocks: list[BlockIn] | None = None


class ShareEntry(BaseModel):
    target: str = Field(..., min_length=1, max_length=80)
    access: str = Field(default="read", pattern="^(read|contribute|edit)$")


class AccessRequest(BaseModel):
    shared_with: list[ShareEntry] | None = Field(default=None, max_length=50)
    hidden_from: list[str] | None = Field(default=None, max_length=50)
    contributors: list[ShareEntry] | None = Field(default=None, max_length=50)


class ShareUnderlyingData(BaseModel):
    value: bool


class ShareRespond(BaseModel):
    owner: str
    dashboard_id: str
    accept: bool


def _resolve_subject(current_user: dict, workspace: str, dashboard: dict) -> dict | None:
    """Small identity summary for the dashboard hero header — never the whole
    record, and never raises: a subject the viewer has lost access to (or a
    dangling id) just means no hero, not a broken dashboard render."""
    subject_type = dashboard.get("subject_type")
    subject_id = dashboard.get("subject_id")
    if not subject_type or not subject_id:
        return None
    viewer = current_user["name"]
    role = current_user.get("feature_role", "member")
    is_admin = current_user.get("role") == "admin"
    try:
        if subject_type == "contact":
            found = contacts_service.find_contact(viewer, role, is_admin, workspace, subject_id)
            if found is None:
                return None
            _store_user, contact, _access = found
            return {
                "type": "contact", "id": subject_id, "name": contact.get("name") or "",
                "contact_type": contact.get("type"), "gender": contact.get("gender"),
                "photo_ext": contact.get("photo_ext"),
            }
        if subject_type == "asset":
            found = assets_service.find_asset(viewer, workspace, subject_id, is_admin, viewer_role=role)
            if found is None:
                return None
            asset = found["asset"]
            template = assets_service.resolve_template(asset)
            return {
                "type": "asset", "id": subject_id, "name": asset.get("name") or "",
                "icon": (template or {}).get("icon"),
            }
    except Exception:
        return None
    return None


def _find(current_user: dict, workspace: str, dashboard_id: str, need: str = "read"):
    found = dashboards_service.find_dashboard(
        current_user["name"],
        current_user.get("feature_role", "member"),
        current_user.get("role") == "admin",
        workspace,
        dashboard_id,
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if _ACCESS_ORDER.get(found["access"], -1) < _ACCESS_ORDER[need]:
        raise HTTPException(status_code=403, detail="You don't have access to change this dashboard.")
    return found


@router.get("")
def list_dashboards(
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    viewer = current_user["name"]
    role = current_user.get("feature_role", "member")
    is_admin = current_user.get("role") == "admin"
    items = dashboards_service.list_visible_dashboards(viewer, role, is_admin, workspace)
    saved_default = (current_user.get("default_dashboard_id") or {}).get(workspace)
    default_id = dashboards_service.resolve_default_dashboard_id(
        viewer, role, is_admin, workspace, saved_default
    )
    return {"items": items, "default_id": default_id}


@router.post("")
def create_dashboard(
    body: DashboardCreate,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    viewer = current_user["name"]
    if body.pool:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        store_user = dashboards_service.pool_for(workspace)
    else:
        store_user = viewer
    try:
        dashboard = dashboards_service.create_dashboard(
            store_user, workspace, viewer, body.name, body.icon,
            template_id=body.template_id, subject_id=body.subject_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return dashboard


# ---------------------------------------------------------------------------
# Templates — admin-managed global + per-user personal. Declared before
# /{dashboard_id} so FastAPI never swallows "templates" as a dashboard id
# (same route-ordering rule assets.py's own template routes follow).
# ---------------------------------------------------------------------------


def _is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


def _template_or_404(tid: str):
    found = dashboard_templates_service._find_template(tid)
    if found is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return found


def _require_template_manage(tid: str, user: dict):
    owner, _ = _template_or_404(tid)
    if owner == dashboard_templates_service.GLOBAL_OWNER:
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Global templates are admin-managed")
    elif owner != user["name"] and not _is_admin(user):
        raise HTTPException(status_code=403, detail="You can only manage your own templates")
    return owner


@router.get("/templates")
def list_templates(current_user: dict = Depends(_require_dashboards)):
    return dashboard_templates_service.visible_templates(
        current_user["name"],
        is_admin=_is_admin(current_user),
        feature_role=current_user.get("feature_role", "member"),
    )


@router.post("/templates", status_code=201)
def create_template(
    req: TemplateCreate,
    current_user: dict = Depends(_require_dashboards),
    _rl: None = Depends(_write_limit),
):
    is_global = req.owner == "global"
    if is_global and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can create global templates")
    owner = dashboard_templates_service.GLOBAL_OWNER if is_global else current_user["name"]
    try:
        return dashboard_templates_service.create_template(
            req.model_dump(exclude={"owner"}), owner=owner
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/templates/{tid}")
def update_template(
    tid: str,
    req: TemplateUpdate,
    current_user: dict = Depends(_require_dashboards),
    _rl: None = Depends(_write_limit),
):
    _require_template_manage(tid, current_user)
    try:
        result = dashboard_templates_service.update_template(tid, req.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.delete("/templates/{tid}", status_code=204)
def delete_template(
    tid: str,
    current_user: dict = Depends(_require_dashboards),
    _rl: None = Depends(_write_limit),
):
    _require_template_manage(tid, current_user)
    try:
        if not dashboard_templates_service.delete_template(tid):
            raise HTTPException(status_code=404, detail="Template not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/templates/{tid}/access")
def update_template_access(
    tid: str,
    req: TemplateAccessUpdate,
    current_user: dict = Depends(_require_dashboards),
    _rl: None = Depends(_write_limit),
):
    owner = _require_template_manage(tid, current_user)
    try:
        if owner == dashboard_templates_service.GLOBAL_OWNER:
            result = dashboard_templates_service.update_template(
                tid, {"restrict_roles": req.restrict_roles or []}
            )
        else:
            result = dashboard_templates_service.share_template(
                owner,
                tid,
                [s.model_dump() for s in (req.shared_with or [])],
                by=current_user["name"],
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.post("/templates/{tid}/leave", status_code=204)
def leave_template(
    tid: str,
    current_user: dict = Depends(_require_dashboards),
):
    owner, _ = _template_or_404(tid)
    if owner == dashboard_templates_service.GLOBAL_OWNER:
        raise HTTPException(status_code=400, detail="Global templates can't be left")
    dashboard_templates_service.leave_template_share(current_user["name"], owner, tid)


@router.post("/templates/shares/respond")
def respond_to_template_share(
    body: TemplateShareRespond,
    current_user: dict = Depends(_require_dashboards),
):
    changed = dashboard_templates_service.respond_to_template_share(
        current_user["name"], body.model_dump(exclude={"accept"}), body.accept
    )
    return {"ok": changed}


@router.get("/catalog")
def get_catalog(current_user: dict = Depends(_require_dashboards)):
    return catalog(current_user.get("role") == "admin")


@router.get("/members")
def list_members(current_user: dict = Depends(_require_dashboards)):
    """Member display names for the share/hide pickers. Mirrors assets.py's list_members."""
    from services.auth_service import list_users

    return [{"name": u["name"]} for u in list_users()]


@router.get("/roles")
def list_roles(current_user: dict = Depends(_require_dashboards)):
    """Feature-role names for the share-by-role picker."""
    from services.features_service import load_features

    return sorted((load_features().get("roles") or {}).keys())


@router.get("/references/{module}/{record_id}")
def get_references(
    module: str,
    record_id: str,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    return dashboard_index.references_for(
        module,
        record_id,
        current_user["name"],
        current_user.get("feature_role", "member"),
        current_user.get("role") == "admin",
        workspace,
    )


@router.get("/{dashboard_id}")
def get_dashboard(
    dashboard_id: str,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    found = _find(current_user, workspace, dashboard_id)
    return {**found["dashboard"], "_owner": found["relation"], "_access": found["access"]}


@router.get("/{dashboard_id}/render")
def get_render(
    dashboard_id: str,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    found = _find(current_user, workspace, dashboard_id)
    viewer = current_user["name"]
    role = current_user.get("feature_role", "member")
    is_admin = current_user.get("role") == "admin"
    blocks = render_dashboard(found["dashboard"], viewer, role, is_admin, workspace, found["access"])
    template_id = found["dashboard"].get("template_id")
    template = dashboard_templates_service.get_template_by_id(template_id) if template_id else None
    return {
        "id": found["dashboard"]["id"],
        "name": found["dashboard"]["name"],
        "icon": found["dashboard"]["icon"],
        "owner": found["dashboard"]["owner"],
        "template_id": template_id,
        "template_label": template.get("label") if template else None,
        "subject_type": found["dashboard"].get("subject_type"),
        "subject_id": found["dashboard"].get("subject_id"),
        "subject": _resolve_subject(current_user, workspace, found["dashboard"]),
        "share_underlying_data": found["dashboard"].get("share_underlying_data", False),
        "shared_with": found["dashboard"].get("shared_with", []),
        "hidden_from": found["dashboard"].get("hidden_from", []),
        "contributors": found["dashboard"].get("contributors", []),
        "_access": found["access"],
        "_relation": found["relation"],
        "blocks": blocks,
    }


@router.patch("/{dashboard_id}")
def update_dashboard(
    dashboard_id: str,
    body: DashboardUpdate,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    found = _find(current_user, workspace, dashboard_id, need="contribute")
    updates = body.model_dump(exclude_unset=True)
    try:
        dashboard = dashboards_service.update_dashboard(
            found["store"], found["store_workspace"], dashboard_id, updates, by=current_user["name"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return dashboard


@router.put("/{dashboard_id}/access")
def update_access(
    dashboard_id: str,
    body: AccessRequest,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    found = _find(current_user, workspace, dashboard_id, need="edit")
    try:
        dashboard = dashboards_service.update_access(
            found["store"],
            workspace,
            dashboard_id,
            shared_with=[s.model_dump() for s in body.shared_with] if body.shared_with is not None else None,
            hidden_from=body.hidden_from,
            contributors=[c.model_dump() for c in body.contributors] if body.contributors is not None else None,
            by=current_user["name"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return dashboard


@router.put("/{dashboard_id}/subject")
def set_subject(
    dashboard_id: str,
    body: SubjectUpdate,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """Contribute-tier, same as editing blocks — changing which contact/asset
    a templated dashboard is about is a content edit, not a sharing change."""
    found = _find(current_user, workspace, dashboard_id, need="contribute")
    try:
        dashboard = dashboards_service.set_subject(
            found["store"], found["store_workspace"], dashboard_id, body.subject_id, by=current_user["name"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dashboard


@router.post("/{dashboard_id}/detach-template")
def detach_template(
    dashboard_id: str,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    found = _find(current_user, workspace, dashboard_id, need="edit")
    dashboard = dashboards_service.detach_template(
        found["store"], found["store_workspace"], dashboard_id, by=current_user["name"]
    )
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dashboard


@router.put("/{dashboard_id}/share-underlying-data")
def set_share_underlying_data(
    dashboard_id: str,
    body: ShareUnderlyingData,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    found = _find(current_user, workspace, dashboard_id)
    try:
        dashboard = dashboards_service.set_share_underlying_data(
            found["store"], workspace, dashboard_id, body.value, by=current_user["name"]
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dashboard


@router.delete("/{dashboard_id}", status_code=204)
def delete_dashboard(
    dashboard_id: str,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    found = _find(current_user, workspace, dashboard_id, need="edit")
    if found["relation"] not in ("own", "pool"):
        raise HTTPException(status_code=403, detail="Only the owner or a pool admin can delete this dashboard.")
    try:
        dashboards_service.delete_dashboard(
            found["store"], found["store_workspace"], dashboard_id, current_user.get("role") == "admin"
        )
    except ValueError as e:
        if str(e) == "floor_of_one":
            raise HTTPException(
                status_code=409, detail="This is your only dashboard — it can't be deleted."
            )
        raise HTTPException(status_code=404, detail="Dashboard not found")


@router.post("/{dashboard_id}/leave", status_code=204)
def leave_dashboard(
    dashboard_id: str,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    found = _find(current_user, workspace, dashboard_id)
    if found["relation"] != "shared":
        raise HTTPException(status_code=400, detail="Not a shared dashboard")
    dashboards_service.leave_share(current_user["name"], found["store"], workspace, dashboard_id)


@router.post("/shares/respond")
def respond_to_share(
    body: ShareRespond,
    current_user: dict = Depends(_require_dashboards),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    changed = dashboards_service.respond_to_share(
        current_user["name"], body.owner, workspace, body.dashboard_id, body.accept
    )
    return {"ok": changed}
