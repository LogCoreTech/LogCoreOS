"""Trash bin — list/restore/purge for soft-deleted records across every
module. Core infrastructure, not itself an installable module (mirrors
routers/brain.py's own plain Depends(get_current_user) gating, since Trash
has no per-module on/off toggle of its own) — see services/trash_service.py
for the actual soft-delete/restore/purge logic and its module-registry
dispatch mechanism.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.auth import get_current_user, get_workspace
from services import trash_service

router = APIRouter()


def _require_allowed_store(current_user: dict, workspace: str, store_user: str) -> None:
    """A caller-supplied store_user must resolve to their own store or an
    enabled pool's store — never trusted blindly, since restore()/purge_one()
    otherwise have no other check standing between an arbitrary store_user
    and another user's trash contents."""
    allowed = {s for s, _ in trash_service.allowed_stores_for(current_user, workspace)}
    if store_user not in allowed:
        raise HTTPException(status_code=403, detail="Access denied")


@router.get("")
def list_trash(
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    return trash_service.list_trash_for_user(current_user, workspace)


class TrashItemRequest(BaseModel):
    store_user: str
    entry_id: str


@router.post("/restore")
def restore_entry(
    req: TrashItemRequest,
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    _require_allowed_store(current_user, workspace, req.store_user)
    try:
        return trash_service.restore(
            store_user=req.store_user,
            workspace=workspace,
            entry_id=req.entry_id,
            actor=current_user["name"],
        )
    except trash_service.TrashModuleUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/purge")
def purge_entry(
    req: TrashItemRequest,
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    _require_allowed_store(current_user, workspace, req.store_user)
    if not trash_service.purge_one(
        store_user=req.store_user, workspace=workspace, entry_id=req.entry_id
    ):
        raise HTTPException(status_code=404, detail="Trash entry not found")
    return {"ok": True}


class BulkTrashRequest(BaseModel):
    items: list[TrashItemRequest]
    action: str  # "restore" | "purge"


@router.post("/bulk")
def bulk_trash_action(
    req: BulkTrashRequest,
    current_user: dict = Depends(get_current_user),
    workspace: str = Depends(get_workspace),
):
    if req.action not in ("restore", "purge"):
        raise HTTPException(status_code=400, detail="action must be 'restore' or 'purge'")

    allowed = {s for s, _ in trash_service.allowed_stores_for(current_user, workspace)}
    results = []
    for item in req.items:
        if item.store_user not in allowed:
            results.append({"entry_id": item.entry_id, "ok": False, "error": "Access denied"})
            continue
        try:
            if req.action == "restore":
                trash_service.restore(
                    store_user=item.store_user,
                    workspace=workspace,
                    entry_id=item.entry_id,
                    actor=current_user["name"],
                )
            else:
                if not trash_service.purge_one(
                    store_user=item.store_user, workspace=workspace, entry_id=item.entry_id
                ):
                    raise ValueError("Trash entry not found")
            results.append({"entry_id": item.entry_id, "ok": True})
        except (trash_service.TrashModuleUnavailable, ValueError) as exc:
            results.append({"entry_id": item.entry_id, "ok": False, "error": str(exc)})
    return {"results": results}
