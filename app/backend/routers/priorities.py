from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.auth import get_current_user, get_workspace, require_admin
from services.auth_service import today_for_user
from services.file_service import read_json, user_path, write_json
from services.profile_service import get_priority_order
from services.rate_limiter import rate_limit

router = APIRouter()
_write_limit = rate_limit(10, 60)


@router.get("")
def get_priorities(
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    name = current_user["name"]
    # Daily override is personal-only (a per-day focus choice, not workspace-specific)
    override_file = user_path(name) / "Tasks" / "daily_override.json"
    if override_file.exists():
        data = read_json(override_file, default={})
        today = today_for_user(name).isoformat()
        if data.get("date") == today and data.get("order"):
            return {"order": data["order"]}
    return {"order": get_priority_order(name, workspace)}


class OverrideRequest(BaseModel):
    order: list[str] = Field(..., min_length=1, max_length=20)


@router.post("/override")
def save_override(req: OverrideRequest, current_user: dict = Depends(get_current_user)):
    name = current_user["name"]
    override_file = user_path(name) / "Tasks" / "daily_override.json"
    today = today_for_user(name).isoformat()
    write_json(override_file, {"order": req.order, "date": today})
    return {"ok": True}


class PoolPrioritiesRequest(BaseModel):
    household: list[str] | None = Field(None, max_length=20)
    team: list[str] | None = Field(None, max_length=20)


@router.get("/pool")
def get_pool_priorities(_admin: dict = Depends(require_admin)):
    """Return the category order for household and team pools (admin only)."""
    return {
        "household": get_priority_order("_household"),
        "team": get_priority_order("_team"),
    }


@router.put("/pool")
def set_pool_priorities(
    req: PoolPrioritiesRequest,
    _admin: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    """Set the category order for household and/or team pools (admin only)."""
    if req.household is not None:
        pool_path = user_path("_household") / "profile.json"
        existing = read_json(pool_path, default={})
        existing["priority_order"] = req.household
        write_json(pool_path, existing)
    if req.team is not None:
        pool_path = user_path("_team") / "profile.json"
        existing = read_json(pool_path, default={})
        existing["priority_order"] = req.team
        write_json(pool_path, existing)
    return {"ok": True}
