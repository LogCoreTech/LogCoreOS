"""Finance sharing endpoints: book/account audience, handshake, leave, pickers.

Personal book shares are per-user REQUESTS (accept/decline via the bell,
exactly like assets); pool books take contributor grants instead (already
workspace-visible, no handshake). All access resolution stays server-side in
finance_service._resolve_book_access — these endpoints only mutate audience."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_workspace, require_module
from routers.finance import _find_or_404, _validate_id
from services import auth_service, finance_service
from services.rate_limiter import rate_limit

_require_finance = require_module("finance")
_read_limit = rate_limit(30, 60)
_write_limit = rate_limit(30, 60)

router = APIRouter()


class ShareEntry(BaseModel):
    target: str = Field(..., min_length=1, max_length=80)
    access: str = Field(default="read", pattern="^(read|contribute|edit)$")
    caps: dict | None = None


class AccessRequest(BaseModel):
    shared_with: list[ShareEntry] | None = Field(default=None, max_length=50)
    hidden_from: list[str] | None = Field(default=None, max_length=50)
    contributors: list[ShareEntry] | None = Field(default=None, max_length=50)


class ShareRespond(BaseModel):
    notif_id: str
    accept: bool


def _require_owner_or_pool_admin(current_user: dict, store_user: str) -> None:
    if finance_service.is_pool(store_user):
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins manage pool book contributors")
    elif store_user != current_user["name"]:
        raise HTTPException(status_code=403, detail="Only the owner can change sharing")


def _notify_share_requests(owner: str, workspace: str, book: dict, users: list[str]) -> None:
    try:
        from services.suggestions_service import notify_user

        for name in users:
            notify_user(
                name,
                "💵 Finance book shared with you",
                f"{owner} wants to share the book “{book['name']}” with you. "
                "Accept to see it in your Finance page.",
                source="finance",
                action={
                    "type": "finance_share",
                    "owner": owner,
                    "workspace": workspace,
                    "book_id": book["id"],
                },
                url="/finance",
            )
    except Exception:
        pass  # share persists even if notification delivery hiccups


@router.put("/books/{book_id}/access")
def update_book_access(
    book_id: str,
    req: AccessRequest,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, _access = _find_or_404(current_user, workspace, book_id)
    _require_owner_or_pool_admin(current_user, store_user)
    try:
        _record, to_notify = finance_service.update_access(
            store_user,
            workspace,
            book_id,
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
    _notify_share_requests(store_user, workspace, book, to_notify)
    fresh = finance_service.get_book(store_user, workspace, book_id)
    return finance_service.annotate(fresh, store_user, current_user["name"], "edit")


@router.put("/books/{book_id}/accounts/{account_id}/access")
def update_account_access(
    book_id: str,
    account_id: str,
    req: AccessRequest,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, _access = _find_or_404(current_user, workspace, book_id)
    _require_owner_or_pool_admin(current_user, store_user)
    _validate_id(account_id, "account ID")
    if req.hidden_from is not None:
        raise HTTPException(status_code=400, detail="hidden_from lives on the book, not accounts")
    try:
        record, to_notify = finance_service.update_access(
            store_user,
            workspace,
            book_id,
            shared_with=(
                [e.model_dump() for e in req.shared_with] if req.shared_with is not None else None
            ),
            contributors=(
                [e.model_dump() for e in req.contributors] if req.contributors is not None else None
            ),
            account_id=account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _notify_share_requests(store_user, workspace, book, to_notify)
    return record


@router.post("/shares/respond")
def respond_share(
    req: ShareRespond,
    current_user: dict = Depends(_require_finance),
    _rl: None = Depends(_write_limit),
):
    from services import suggestions_service

    notif = suggestions_service.resolve_notification(current_user["name"], req.notif_id)
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    action = notif.get("action") or {}
    if action.get("type") != "finance_share":
        raise HTTPException(status_code=400, detail="Not a finance share request")
    finance_service.respond_share(
        current_user["name"],
        action.get("owner", ""),
        action.get("workspace", "personal"),
        action.get("book_id", ""),
        req.accept,
    )
    return {"ok": True}


@router.post("/books/{book_id}/leave")
def leave_book(
    book_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    found = _find_or_404(current_user, workspace, book_id)
    store_user, _book, _access = found
    if store_user == current_user["name"] or finance_service.is_pool(store_user):
        raise HTTPException(status_code=400, detail="You can only leave a book shared with you")
    finance_service.respond_share(
        current_user["name"], store_user, workspace, book_id, accept=False
    )
    return {"ok": True}


@router.get("/members")
def list_members(
    current_user: dict = Depends(_require_finance),
    _rl: None = Depends(_read_limit),
):
    """Member display names for the share/hide pickers (names only)."""
    return [{"name": u["name"]} for u in auth_service.list_users()]


@router.get("/roles")
def list_roles(
    current_user: dict = Depends(_require_finance),
    _rl: None = Depends(_read_limit),
):
    from services.features_service import load_features

    return sorted((load_features().get("roles") or {}).keys())
