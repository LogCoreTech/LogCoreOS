"""Notes module — markdown notes with folders + asset-style sharing.

Reads/writes route through notes_service access resolution so shared and pool
(household/team) notes are reachable server-side; the frontend never decides
access. contribute = edit note content; edit = full (move/delete/reshare)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_workspace, require_module
from services import auth_service, notes_service
from services.rate_limiter import rate_limit

_require_notes = require_module("notes")
_read_limit = rate_limit(60, 60)
_write_limit = rate_limit(30, 60)

router = APIRouter()

_MAX_CONTENT = 512_000


class NoteCreate(BaseModel):
    path: str = Field(..., min_length=1, max_length=500)
    content: str = Field(default="", max_length=_MAX_CONTENT)
    pool: bool = False


class NoteUpdate(BaseModel):
    content: str = Field(..., max_length=_MAX_CONTENT)


class FolderCreate(BaseModel):
    path: str = Field(..., min_length=1, max_length=500)
    pool: bool = False


class MoveItem(BaseModel):
    from_path: str = Field(..., min_length=1, max_length=500)
    to_path: str = Field(..., min_length=1, max_length=500)
    type: str = Field(..., pattern="^(note|folder)$")


class ShareEntry(BaseModel):
    target: str = Field(..., min_length=1, max_length=80)
    access: str = Field(default="read", pattern="^(read|contribute|edit)$")


class AccessRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=500)
    shared_with: list[ShareEntry] | None = Field(default=None, max_length=50)
    hidden_from: list[str] | None = Field(default=None, max_length=50)
    contributors: list[ShareEntry] | None = Field(default=None, max_length=50)


class ShareRespond(BaseModel):
    notif_id: str
    accept: bool


class LeaveRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=500)


def _resolve(current_user: dict, workspace: str, path: str, need: str):
    """Return the store_user for a path the viewer can reach at >= `need`
    access (read|contribute|edit), or 404/403."""
    try:
        found = notes_service.find_note_store(
            current_user["name"],
            current_user.get("feature_role", "member"),
            current_user.get("role") == "admin",
            workspace,
            path,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not found:
        raise HTTPException(status_code=404, detail="Note not found")
    store_user, access = found
    order = {"read": 0, "contribute": 1, "edit": 2}
    if order.get(access, -1) < order[need]:
        raise HTTPException(status_code=403, detail="You don't have access to change this note.")
    return store_user


@router.get("")
def list_notes(
    current_user: dict = Depends(_require_notes),
    workspace: str = Depends(get_workspace),
):
    return notes_service.list_visible_notes(
        current_user["name"],
        current_user.get("feature_role", "member"),
        current_user.get("role") == "admin",
        workspace,
    )


@router.get("/members")
def list_members(current_user: dict = Depends(_require_notes), _rl: None = Depends(_read_limit)):
    return [{"name": u["name"]} for u in auth_service.list_users()]


@router.get("/roles")
def list_roles(current_user: dict = Depends(_require_notes), _rl: None = Depends(_read_limit)):
    from services.features_service import load_features

    return sorted((load_features().get("roles") or {}).keys())


@router.get("/file/{path:path}")
def get_note(
    path: str,
    current_user: dict = Depends(_require_notes),
    workspace: str = Depends(get_workspace),
):
    store_user = _resolve(current_user, workspace, path, "read")
    try:
        note = notes_service.get_note(store_user, path, workspace)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.post("/file", status_code=201)
def create_note(
    req: NoteCreate,
    current_user: dict = Depends(_require_notes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user = current_user["name"]
    if req.pool:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins create shared-pool notes")
        store_user = notes_service.pool_for(workspace)
    try:
        return notes_service.create_note(store_user, req.path, req.content, workspace)
    except ValueError as e:
        status = 409 if "already exists" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.put("/file/{path:path}")
def update_note(
    path: str,
    req: NoteUpdate,
    current_user: dict = Depends(_require_notes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user = _resolve(current_user, workspace, path, "contribute")
    try:
        result = notes_service.update_note(store_user, path, req.content, workspace)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Note not found")
    return result


@router.delete("/file/{path:path}")
def delete_note(
    path: str,
    current_user: dict = Depends(_require_notes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user = _resolve(current_user, workspace, path, "edit")
    try:
        deleted = notes_service.delete_note(store_user, path, workspace)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}


@router.post("/folder", status_code=201)
def create_folder(
    req: FolderCreate,
    current_user: dict = Depends(_require_notes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user = current_user["name"]
    if req.pool:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins create shared-pool folders")
        store_user = notes_service.pool_for(workspace)
    try:
        return notes_service.create_folder(store_user, req.path, workspace)
    except ValueError as e:
        status = 409 if "already exists" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.delete("/folder/{path:path}")
def delete_folder(
    path: str,
    current_user: dict = Depends(_require_notes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user = _resolve(current_user, workspace, path, "edit")
    try:
        notes_service.delete_folder(store_user, path, workspace)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/move")
def move_item(
    req: MoveItem,
    current_user: dict = Depends(_require_notes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    # Move is same-store, edit-level; both endpoints resolve to the same store.
    store_user = _resolve(current_user, workspace, req.from_path, "edit")
    try:
        return notes_service.move_item(store_user, req.from_path, req.to_path, req.type, workspace)
    except ValueError as e:
        status = (
            409 if "already exists" in str(e) else 404 if "not found" in str(e).lower() else 400
        )
        raise HTTPException(status_code=status, detail=str(e))


# ── Sharing ────────────────────────────────────────────────────────────────────


def _require_owner_or_pool_admin(current_user: dict, store_user: str) -> None:
    if notes_service.is_pool(store_user):
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins manage pool-note sharing")
    elif store_user != current_user["name"]:
        raise HTTPException(status_code=403, detail="Only the owner can change sharing")


def _notify_share_requests(owner: str, workspace: str, path: str, users: list[str]) -> None:
    try:
        from services.suggestions_service import notify_user

        for name in users:
            notify_user(
                name,
                "📝 Note shared with you",
                f"{owner} shared the note “{path.split('/')[-1]}” with you.",
                source="notes",
                action={
                    "type": "notes_share",
                    "owner": owner,
                    "workspace": workspace,
                    "path": path,
                },
                url="/notes",
            )
    except Exception:
        pass


@router.put("/access")
def update_access(
    req: AccessRequest,
    current_user: dict = Depends(_require_notes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user = _resolve(current_user, workspace, req.path, "edit")
    _require_owner_or_pool_admin(current_user, store_user)
    try:
        _entry, to_notify = notes_service.update_access(
            store_user,
            workspace,
            req.path,
            shared_with=(
                [e.model_dump() for e in req.shared_with] if req.shared_with is not None else None
            ),
            hidden_from=req.hidden_from,
            contributors=(
                [e.model_dump() for e in req.contributors] if req.contributors is not None else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _notify_share_requests(store_user, workspace, req.path, to_notify)
    return {"ok": True}


@router.post("/shares/respond")
def respond_share(
    req: ShareRespond,
    current_user: dict = Depends(_require_notes),
    _rl: None = Depends(_write_limit),
):
    from services import suggestions_service

    notif = suggestions_service.resolve_notification(current_user["name"], req.notif_id)
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    action = notif.get("action") or {}
    if action.get("type") != "notes_share":
        raise HTTPException(status_code=400, detail="Not a note share request")
    notes_service.respond_share(
        current_user["name"],
        action.get("owner", ""),
        action.get("workspace", "personal"),
        action.get("path", ""),
        req.accept,
    )
    return {"ok": True}


@router.post("/leave")
def leave_note(
    req: LeaveRequest,
    current_user: dict = Depends(_require_notes),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    found = notes_service.find_note_store(
        current_user["name"],
        current_user.get("feature_role", "member"),
        current_user.get("role") == "admin",
        workspace,
        req.path,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Note not found")
    store_user, _access = found
    if store_user == current_user["name"] or notes_service.is_pool(store_user):
        raise HTTPException(status_code=400, detail="You can only leave a note shared with you")
    notes_service.respond_share(current_user["name"], store_user, workspace, req.path, accept=False)
    return {"ok": True}
