"""Contacts sharing endpoints: access grants, handshake, leave, member/role
pickers — mirrors module_packages/finance/backend/router_sharing.py's own
split exactly (finance's own list_members/list_roles picker endpoints live
in its sharing file too, not its core router).

Personal contact shares are per-user REQUESTS (accept/decline via the bell,
exactly like assets/finance); pool contacts take contributor grants instead
(already workspace-visible, no handshake). All access resolution stays
server-side in contacts_service — these endpoints only mutate audience."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from module_packages.contacts.backend.router import _find_or_404
from routers.auth import get_workspace, require_module
from services import auth_service, contacts_service
from services.rate_limiter import rate_limit

_require_contacts = require_module("contacts")
_read_limit = rate_limit(60, 60)
_write_limit = rate_limit(30, 60)

router = APIRouter()


class ShareEntry(BaseModel):
    target: str = Field(..., min_length=1, max_length=80)
    access: str = Field(default="read", pattern="^(read|contribute|edit)$")


class AccessRequest(BaseModel):
    shared_with: list[ShareEntry] | None = Field(default=None, max_length=50)
    hidden_from: list[str] | None = Field(default=None, max_length=50)
    contributors: list[ShareEntry] | None = Field(default=None, max_length=50)


class ShareRespond(BaseModel):
    notif_id: str
    accept: bool


def _require_owner_or_pool_admin(current_user: dict, store_user: str) -> None:
    if contacts_service.is_pool(store_user):
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins manage pool contacts")
    elif store_user != current_user["name"]:
        raise HTTPException(status_code=403, detail="Only the owner can change sharing")


def _notify_share_requests(owner: str, workspace: str, contact: dict, users: list[str]) -> None:
    try:
        from services.suggestions_service import notify_user

        for name in users:
            notify_user(
                name,
                "👥 Contact shared with you",
                f"{owner} wants to share the contact “{contact['name']}” with you.",
                source="contacts",
                action={
                    "type": "contacts_share",
                    "owner": owner,
                    "workspace": workspace,
                    "contact_id": contact["id"],
                },
                url="/contacts",
            )
    except Exception:
        pass


@router.put("/{contact_id}/access")
def update_contact_access(
    contact_id: str,
    req: AccessRequest,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, _access = _find_or_404(current_user, workspace, contact_id)
    _require_owner_or_pool_admin(current_user, store_user)
    ws = contacts_service.effective_workspace(store_user, contact, workspace)
    try:
        record, to_notify = contacts_service.update_access(
            store_user,
            ws,
            contact_id,
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
    _notify_share_requests(store_user, ws, contact, to_notify)
    return contacts_service.annotate(record, store_user, current_user["name"], "edit")


@router.post("/shares/respond")
def respond_share(
    req: ShareRespond,
    current_user: dict = Depends(_require_contacts),
    _rl: None = Depends(_write_limit),
):
    from services import suggestions_service

    notif = suggestions_service.resolve_notification(current_user["name"], req.notif_id)
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    action = notif.get("action") or {}
    if action.get("type") != "contacts_share":
        raise HTTPException(status_code=400, detail="Not a contact share request")
    contacts_service.respond_share(
        current_user["name"],
        action.get("owner", ""),
        action.get("workspace", "personal"),
        action.get("contact_id", ""),
        req.accept,
    )
    return {"ok": True}


@router.post("/{contact_id}/leave")
def leave_contact(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _contact, _access = _find_or_404(current_user, workspace, contact_id)
    if store_user == current_user["name"] or contacts_service.is_pool(store_user):
        raise HTTPException(status_code=400, detail="You can only leave a contact shared with you")
    contacts_service.respond_share(
        current_user["name"], store_user, workspace, contact_id, accept=False
    )
    return {"ok": True}


@router.get("/members")
def list_members(
    current_user: dict = Depends(_require_contacts),
    _rl: None = Depends(_read_limit),
):
    return [{"name": u["name"]} for u in auth_service.list_users()]


@router.get("/roles")
def list_roles(
    current_user: dict = Depends(_require_contacts),
    _rl: None = Depends(_read_limit),
):
    from services.features_service import load_features

    return sorted((load_features().get("roles") or {}).keys())
