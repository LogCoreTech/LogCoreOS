"""Homes: house CRUD (personal + household/team pool) + the per-house
cross-module tagged-items view. Pool resolution mirrors
module_packages/goals/backend/router.py's own `_pool_user`/`_pool_id`/
`_require_pool_write`/`_store_for` shape verbatim — reads need only
require_module("homes"); pool WRITES additionally need pool_edit or admin,
exactly like Goals'/Household's/Team's own existing write endpoints.

IDOR note: every id-taking endpoint resolves to exactly one of two stores —
the caller's own (`current_user["name"]`, never client-supplied) or the
workspace's pool (only if pool-installed, and only if the caller actually
has pool_edit/admin for WRITES) — there is no third "look up any home_id
anywhere" path, so a bare home_id can never be used to probe a different,
unrelated user's personal store."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from module_packages.homes.backend import service as homes_service
from routers.auth import get_workspace, require_module
from services import search_service
from services.rate_limiter import rate_limit

_require_homes = require_module("homes")
_read_limit = rate_limit(60, 60)
_write_limit = rate_limit(30, 60)
_items_limit = rate_limit(30, 60)  # the aggregation endpoint fans out across every active module

router = APIRouter()


def _pool_user(workspace: str) -> str:
    return "_household" if workspace == "personal" else "_team"


def _pool_id(workspace: str) -> str:
    return "household" if workspace == "personal" else "team"


def _pool_installed(workspace: str) -> bool:
    from services import mod_store_service

    return mod_store_service.is_installed(_pool_id(workspace))


def _require_pool_write(workspace: str, current_user: dict) -> None:
    if current_user.get("role") == "admin":
        return
    if _pool_id(workspace) in (current_user.get("pool_edit") or []):
        return
    raise HTTPException(status_code=403, detail="You don't have permission to make changes here.")


def _store_for(pool: bool, workspace: str, current_user: dict) -> tuple[str, str]:
    if pool:
        return _pool_user(workspace), "personal"
    return current_user["name"], workspace


def _validate_id(home_id: str) -> str:
    try:
        UUID(home_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid home ID format")
    return home_id


class HomeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    ownership_type: str = Field(..., pattern="^(rent|own)$")
    icon: str | None = Field(None, max_length=8)
    address: str | None = Field(None, max_length=2000)
    notes: str | None = Field(None, max_length=2000)
    rent: dict | None = None
    own: dict | None = None
    pool: bool = False


class HomeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    ownership_type: str | None = Field(None, pattern="^(rent|own)$")
    icon: str | None = Field(None, max_length=8)
    address: str | None = Field(None, max_length=2000)
    notes: str | None = Field(None, max_length=2000)
    rent: dict | None = None
    own: dict | None = None
    pool: bool = False


class BulkDeleteRequest(BaseModel):
    ids: list[str] = Field(..., max_length=200)
    pool: bool = False


@router.get("")
def list_homes(
    current_user: dict = Depends(_require_homes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    """Caller's own homes + the workspace's pool homes if that pool module
    is installed — matches Goals'/Tasks'/Notes' own default (visible to
    every member, not gated behind a contributors list). Pool homes carry
    an `_owner` label ("household"/"team") for the frontend chip badge —
    own-store homes carry none, matching Finance's own book-list
    convention (absence of `_owner` means "mine")."""
    own = homes_service.list_homes(current_user["name"], workspace)
    if not _pool_installed(workspace):
        return own
    pool_user = _pool_user(workspace)
    pool_homes = [
        {**h, "_owner": _pool_id(workspace)}
        for h in homes_service.list_homes(pool_user, "personal")
    ]
    return own + pool_homes


@router.post("", status_code=201)
def create_home(
    req: HomeCreate,
    current_user: dict = Depends(_require_homes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    if req.pool:
        _require_pool_write(workspace, current_user)
    store_user, store_ws = _store_for(req.pool, workspace, current_user)
    payload = req.model_dump(exclude={"pool"})
    payload["created_by"] = current_user["name"]
    try:
        return homes_service.create_home(store_user, payload, store_ws)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{home_id}")
def get_home(
    home_id: str,
    pool: bool = False,
    current_user: dict = Depends(_require_homes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    _validate_id(home_id)
    if pool and not _pool_installed(workspace):
        raise HTTPException(status_code=404, detail="Home not found")
    store_user, store_ws = _store_for(pool, workspace, current_user)
    home = homes_service.get_home(store_user, home_id, store_ws)
    if home is None:
        raise HTTPException(status_code=404, detail="Home not found")
    return home


@router.patch("/{home_id}")
def update_home(
    home_id: str,
    req: HomeUpdate,
    current_user: dict = Depends(_require_homes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_id(home_id)
    if req.pool:
        _require_pool_write(workspace, current_user)
    store_user, store_ws = _store_for(req.pool, workspace, current_user)
    # `tag` is deliberately not a field on HomeUpdate at all — there is no
    # request-body key to strip here, it simply cannot be sent.
    updates = req.model_dump(exclude_unset=True, exclude={"pool"})
    try:
        result = homes_service.update_home(store_user, home_id, updates, store_ws)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Home not found")
    return result


@router.delete("/{home_id}", status_code=204)
def delete_home(
    home_id: str,
    pool: bool = False,
    current_user: dict = Depends(_require_homes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_id(home_id)
    if pool:
        _require_pool_write(workspace, current_user)
    store_user, store_ws = _store_for(pool, workspace, current_user)
    if not homes_service.delete_home(
        store_user, home_id, store_ws, deleted_by=current_user["name"]
    ):
        raise HTTPException(status_code=404, detail="Home not found")


@router.post("/bulk-delete")
def bulk_delete_homes(
    req: BulkDeleteRequest,
    current_user: dict = Depends(_require_homes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    if req.pool:
        _require_pool_write(workspace, current_user)
    store_user, store_ws = _store_for(req.pool, workspace, current_user)

    deleted: list[str] = []
    failed: list[dict] = []
    for home_id in req.ids:
        try:
            _validate_id(home_id)
            if not homes_service.delete_home(
                store_user, home_id, store_ws, deleted_by=current_user["name"]
            ):
                failed.append({"id": home_id, "error": "Home not found"})
                continue
            deleted.append(home_id)
        except HTTPException as exc:
            failed.append({"id": home_id, "error": exc.detail})
    return {"deleted": deleted, "failed": failed}


@router.post("/{home_id}/convert-to-pool")
def convert_home_to_pool(
    home_id: str,
    current_user: dict = Depends(_require_homes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """One-way, self-service personal → household/team pool move — same
    "edit access, not admin-only" gate as creating a pool home in the
    first place (`_require_pool_write`), mirroring Contacts' own
    `convert_contact_to_pool`/Assets' own `convert_to_pool` action. No
    reverse endpoint exists anywhere in this app yet (Assets/Contacts
    don't have one either) — not inventing one here either; a home that
    needs to come back out of the pool is deleted (Trash-recoverable) and
    recreated personal."""
    _validate_id(home_id)
    if not _pool_installed(workspace):
        raise HTTPException(status_code=404, detail="Home not found")
    _require_pool_write(workspace, current_user)
    pool_user = _pool_user(workspace)
    converted = homes_service.convert_to_pool(current_user["name"], home_id, workspace, pool_user)
    if converted is None:
        raise HTTPException(status_code=404, detail="Home not found")
    return {**converted, "_owner": _pool_id(workspace)}


@router.get("/{home_id}/items")
def get_home_items(
    home_id: str,
    pool: bool = False,
    current_user: dict = Depends(_require_homes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_items_limit),
):
    """Everything tagged with this home's own tag, across every active
    module — resolves the home (and therefore access to it) FIRST, then
    searches scoped to that same (store_user, store_workspace); never
    fans out across a store the caller didn't already have access to just
    by resolving the home itself."""
    _validate_id(home_id)
    if pool and not _pool_installed(workspace):
        raise HTTPException(status_code=404, detail="Home not found")
    store_user, store_ws = _store_for(pool, workspace, current_user)
    home = homes_service.get_home(store_user, home_id, store_ws)
    if home is None:
        raise HTTPException(status_code=404, detail="Home not found")

    # search_service.search() is always called with the REAL caller + the
    # REAL requested workspace, exactly like routers/search.py's own thin
    # wrapper — pool visibility is already handled inside each provider
    # (household's/team's own providers hardcode their own pseudo-user
    # store regardless of which `user` is passed; Finance/Contacts/Assets/
    # Notes fold pool visibility into their own single provider via their
    # existing list_visible_*() access checks). No per-request user
    # substitution needed or correct here.
    results = search_service.search(
        "", [home["tag"]], current_user, workspace, per_provider_cap=50, total_cap=200
    )
    return {"home": home, "items": results}
