"""Shared tag vocabulary for Goals + Tasks — see services/tags_service.py's
own docstring for why this stays core with no module gate (mirrors
routers/priorities.py's own shape: login-required, not tied to a single
module, since both Goals and Tasks read from it)."""

from fastapi import APIRouter, Depends

from routers.auth import get_current_user, get_workspace
from services import tags_service

router = APIRouter()


def _pool_user(workspace: str) -> str:
    return "_household" if workspace == "personal" else "_team"


@router.get("")
def get_tags(
    pool: bool = False,
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    """The caller's own tag vocabulary, or their workspace's pool vocabulary
    when pool=true — mirrors goals/backend/router.py's own personal-vs-pool
    store resolution, including the pool-always-resolves-to-workspace=
    "personal" internally rule (see that router's own module docstring)."""
    if pool:
        return {"tags": tags_service.get_tags(_pool_user(workspace), "personal")}
    return {"tags": tags_service.get_tags(current_user["name"], workspace)}
