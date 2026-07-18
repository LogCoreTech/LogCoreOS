"""Help system endpoints — authored help content, What's-New banner state, and
first-run onboarding checklist state.

Help is not a module: these endpoints require auth but have no module gate (like
Settings), so every signed-in user can reach them.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.auth import get_current_user
from services import help_service, whats_new_service
from services.rate_limiter import rate_limit

router = APIRouter()
_help_limit = rate_limit(30, 60)
_write_limit = rate_limit(20, 60)


class OnboardingUpdate(BaseModel):
    dismissed: bool | None = None
    done: list[str] | None = Field(default=None, max_length=30)


@router.get("/content")
def content(
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_help_limit),
):
    """Full authored help content: sections, FAQ, support info, and what's-new."""
    return help_service.get_content()


@router.get("/whats-new")
def whats_new(
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_help_limit),
):
    """Banner state after an update: {version, until, highlights} (empty once expired)."""
    return whats_new_service.get_banner()


@router.get("/onboarding")
def get_onboarding(
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_help_limit),
):
    """The current user's first-run checklist state."""
    return help_service.get_onboarding(current_user["name"])


@router.put("/onboarding")
def set_onboarding(
    body: OnboardingUpdate,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_write_limit),
):
    """Merge-update the checklist state (mark steps done / dismiss the card)."""
    return help_service.set_onboarding(
        current_user["name"], dismissed=body.dismissed, done=body.done
    )
