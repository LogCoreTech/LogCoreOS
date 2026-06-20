from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user, require_module
from services.rate_limiter import rate_limit
import services.suggestions_service as svc

router = APIRouter()

_require_chat = require_module("chat")
_run_limit = rate_limit(10, 60)


class SuggestionUpdate(BaseModel):
    enabled: bool | None = None
    hour: int | None = Field(None, ge=0, le=23)
    delivery: list[str] | None = None
    days_threshold: int | None = Field(None, ge=1, le=365)


# ---------------------------------------------------------------------------
# Suggestion config
# ---------------------------------------------------------------------------

@router.get("")
def get_suggestions(current_user: dict = Depends(get_current_user)):
    return svc.get_config(current_user["name"])


@router.put("/{suggestion_id}")
def update_suggestion(
    suggestion_id: str,
    body: SuggestionUpdate,
    current_user: dict = Depends(get_current_user),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    return svc.update_config(current_user["name"], suggestion_id, updates)


@router.post("/{suggestion_id}/run")
async def run_suggestion(
    suggestion_id: str,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_run_limit),
):
    result = await svc.run_suggestion_async(current_user["name"], suggestion_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/custom/{suggestion_id}")
def delete_custom_suggestion(
    suggestion_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        import scheduler as sched_mod
        sched_mod.remove_custom_job(current_user["name"], suggestion_id)
    except Exception:
        pass
    deleted = svc.delete_custom(current_user["name"], suggestion_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Custom suggestion not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Notification inbox
# ---------------------------------------------------------------------------

@router.get("/notifications")
def get_notifications(
    limit: int = 20,
    delivery: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    return svc.get_notifications(current_user["name"], limit=limit, delivery=delivery)


@router.post("/notifications/{notif_id}/read")
def mark_notification_read(
    notif_id: str,
    current_user: dict = Depends(get_current_user),
):
    found = svc.mark_read(current_user["name"], notif_id)
    if not found:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.delete("/notifications")
def clear_all_notifications(current_user: dict = Depends(get_current_user)):
    svc.clear_notifications(current_user["name"])
    return {"ok": True}
