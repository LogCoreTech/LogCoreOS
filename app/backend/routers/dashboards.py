"""Dashboards module — standalone, unlimited, user-created custom dashboards.
Reads/writes route through dashboards_service access resolution so shared and
pool (household/team) dashboards are reachable server-side. Reuses the
existing `dashboard` module id — no new require_module registry entry."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_workspace, require_module
from services import dashboard_index, dashboards_service
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
    dashboard = dashboards_service.create_dashboard(store_user, workspace, viewer, body.name, body.icon)
    return dashboard


@router.get("/catalog")
def get_catalog(current_user: dict = Depends(_require_dashboards)):
    return catalog(current_user.get("role") == "admin")


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
    return {
        "id": found["dashboard"]["id"],
        "name": found["dashboard"]["name"],
        "icon": found["dashboard"]["icon"],
        "owner": found["dashboard"]["owner"],
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
