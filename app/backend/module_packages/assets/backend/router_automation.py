"""Assets module: n8n automation API — X-Automation-Token auth, no JWT.

Split out of module_packages/assets/backend/router.py — see that file's
docstring for the full split rationale and why route order matters.
`/automation/*` paths are declared before the core module's bare
`/{asset_id}` routes for the same reason `/templates*` is; `_get_router()`
in manifest.py handles that.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from module_packages.assets.backend.router import _validate_asset_id
from services import assets_service, automations_config
from services.auth_service import get_user_by_name
from services.rate_limiter import rate_limit

_automation_limit = rate_limit(30, 60)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


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


def _require_automation_token(x_automation_token: str = Header("")) -> None:
    if not automations_config.verify_api_token(x_automation_token):
        raise HTTPException(status_code=401, detail="Invalid automation token")


def _automation_store(user: str, workspace: str, read_only: bool = False) -> tuple[str, str]:
    """Resolve the target store: a real user, or _team/_household pool names.

    ``read_only=True`` (the list/export path) restricts the target to the shared
    pool pseudo-users only. The automation API is authenticated by a single
    instance-wide token, so allowing an arbitrary ``user`` on a bulk read would let
    one leaked token dump every user's entire assets store. Writes may still target
    a specific user (that's the intended n8n sync use, and mirrors the Contacts
    automation API's write-only, no-bulk-export design).
    """
    if user in ("_team", "_household"):
        return user, "personal"
    if read_only:
        raise HTTPException(
            status_code=403,
            detail="Automation reads are limited to the _team/_household pools.",
        )
    if get_user_by_name(user) is None:
        raise HTTPException(status_code=404, detail=f"Unknown user {user!r}")
    return user, workspace


@router.get("/automation/assets")
def automation_list_assets(
    user: str,
    workspace: str = "personal",
    template: str | None = None,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    store, store_ws = _automation_store(user, workspace, read_only=True)
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
