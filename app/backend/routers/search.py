"""App-wide search — GET /search?q=&tags=. Mirrors routers/tags.py's own
shape exactly: login-required, no module gate (search isn't owned by any
single module — it fans out across whichever modules are active for this
user). Thin wrapper over services/search_service.py, which does the real
fan-out/filtering work.

2026-09-04 UX Polish Batch item #10 (fast-follow): `cross_workspace` and
`provider` (the "show more" single-provider fetch) query params, both
optional — every existing caller omitting them gets the exact same
single-workspace, all-providers behavior as before. Always calls
`with_totals=True` now so the response carries `provider_totals` alongside
`results` — an additive field, not a breaking shape change for any existing
frontend caller reading just `.results`."""

from fastapi import APIRouter, Depends, Query

from routers.auth import get_current_user, get_workspace
from services import search_service

router = APIRouter()


@router.get("")
def search(
    q: str = Query(default=""),
    tags: list[str] = Query(default=[]),
    cross_workspace: bool = Query(default=False),
    provider: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    return search_service.search(
        q,
        tags,
        current_user,
        workspace,
        cross_workspace=cross_workspace,
        provider=provider,
        with_totals=True,
    )
