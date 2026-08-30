"""App-wide search — GET /search?q=&tags=. Mirrors routers/tags.py's own
shape exactly: login-required, no module gate (search isn't owned by any
single module — it fans out across whichever modules are active for this
user). Thin wrapper over services/search_service.py, which does the real
fan-out/filtering work."""

from fastapi import APIRouter, Depends, Query

from routers.auth import get_current_user, get_workspace
from services import search_service

router = APIRouter()


@router.get("")
def search(
    q: str = Query(default=""),
    tags: list[str] = Query(default=[]),
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    return {"results": search_service.search(q, tags, current_user, workspace)}
