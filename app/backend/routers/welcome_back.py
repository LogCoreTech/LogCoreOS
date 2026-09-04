"""Welcome-back popup — GET /welcome-back/check. Mirrors routers/search.py's
own shape: login-required, no module gate. Thin wrapper over
services/welcome_back_service.py."""

from fastapi import APIRouter, Depends

from routers.auth import get_current_user, get_workspace
from services import presence_service, welcome_back_service

router = APIRouter()


@router.get("/check")
async def check(
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    """Checked once per app load (Layout.jsx). Reads should_show() BEFORE
    touching presence, so this request's own ping can't race the away-check
    it's answering — record_presence() below always runs last, resetting the
    away-timer regardless of the answer, exactly like an ordinary page-visit
    ping would."""
    show = welcome_back_service.should_show(current_user)
    summary = None
    if show and current_user.get("welcome_back_ai_summary_enabled"):
        summary = await welcome_back_service.generate_summary(current_user, workspace)
    presence_service.record_presence(current_user["name"])
    return {"show": show, "summary": summary}
