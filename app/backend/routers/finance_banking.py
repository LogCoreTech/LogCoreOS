"""Finance banking: SimpleFIN connections (admin-managed), CSV import, payee rules.

Connection lifecycle is ADMIN-ONLY (claim/reveal/disconnect/sync) — members
request a connection (admins get a bell/push) and map already-connected bank
accounts onto their own books. Pool-book mapping targets are admin-only too.
The access URL is never returned outside the rate-limited admin reveal.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from routers.auth import get_workspace, require_admin, require_module
from routers.finance import _find_or_404, _require_edit
from services import auth_service, finance_import_service, finance_service, simplefin_service
from services.file_service import simplefin_path
from services.rate_limiter import rate_limit

_require_finance = require_module("finance")
_read_limit = rate_limit(30, 60)
_write_limit = rate_limit(30, 60)
_request_limit = rate_limit(3, 3600)
_claim_limit = rate_limit(5, 3600)
_reveal_limit = rate_limit(3, 3600)
_sync_limit = rate_limit(10, 3600)

router = APIRouter()


class MappingTarget(BaseModel):
    store: str = Field(..., pattern="^(self|household|team)$")
    workspace: str = Field(default="personal", pattern="^(personal|business)$")
    book_id: str
    account_id: str


class MappingEntry(BaseModel):
    simplefin_account_id: str = Field(..., min_length=1, max_length=200)
    bank_name: str = Field(default="", max_length=80)
    account_name: str = Field(default="", max_length=80)
    target: MappingTarget
    enabled: bool = True


class MappingRequest(BaseModel):
    entries: list[MappingEntry] = Field(default_factory=list, max_length=50)


class ClaimRequest(BaseModel):
    user_id: str
    setup_token: str = Field(..., min_length=8, max_length=4000)


class UserRef(BaseModel):
    user_id: str


def _resolve_user(user_id: str) -> dict:
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    return target


# ---------------------------------------------------------------------------
# Member endpoints — request + status + mapping
# ---------------------------------------------------------------------------


@router.post("/simplefin/request")
def request_connection(
    current_user: dict = Depends(_require_finance),
    _rl: None = Depends(_request_limit),
):
    """Ask the admins to set up a bank connection for me."""
    from services.suggestions_service import notify_user

    admins = [u["name"] for u in auth_service.list_users() if u.get("role") == "admin"]
    for admin in admins:
        notify_user(
            admin,
            "🏦 Bank connection request",
            f"{current_user['name']} asked to connect a bank account via SimpleFIN. "
            "Add their setup token in Admin → Bank Connections.",
            source="finance",
            action={"type": "open_admin_banking"},
            url="/admin",
        )
    return {"ok": True, "notified_admins": len(admins)}


@router.get("/simplefin/status")
def my_status(
    current_user: dict = Depends(_require_finance),
    _rl: None = Depends(_read_limit),
):
    return simplefin_service.connection_status(current_user["name"])


@router.get("/simplefin/accounts")
def my_bank_accounts(
    current_user: dict = Depends(_require_finance),
    _rl: None = Depends(_read_limit),
):
    try:
        return simplefin_service.list_bank_accounts(current_user["name"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/simplefin/mapping")
def set_mapping(
    req: MappingRequest,
    current_user: dict = Depends(_require_finance),
    _rl: None = Depends(_write_limit),
):
    try:
        return simplefin_service.set_mapping(
            current_user["name"],
            [e.model_dump() for e in req.entries],
            is_admin=current_user.get("role") == "admin",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Admin endpoints — the connection lifecycle
# ---------------------------------------------------------------------------


@router.get("/simplefin/connections")
def list_connections(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_read_limit),
):
    out = []
    for user in auth_service.list_users():
        status = simplefin_service.connection_status(user["name"])
        out.append(
            {
                "user_id": user["id"],
                "name": user["name"],
                "connected": status.get("connected", False),
                "last_sync": status.get("last_sync"),
                "last_error": status.get("last_error"),
                "mapped_accounts": len(status.get("account_map", []) or []),
            }
        )
    return out


@router.post("/simplefin/claim")
def claim_for_user(
    req: ClaimRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_claim_limit),
):
    target = _resolve_user(req.user_id)
    try:
        status = simplefin_service.claim_and_save(target["name"], req.setup_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    from services.suggestions_service import notify_user

    notify_user(
        target["name"],
        "🏦 Bank connection ready",
        "Your SimpleFIN connection is set up. Open Finance → Bank to map your "
        "bank accounts onto your books.",
        source="finance",
        url="/finance",
    )
    return status


@router.post("/simplefin/reveal")
def reveal_access_url(
    req: UserRef,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_reveal_limit),
):
    """Return the stored access URL so the user can take their token elsewhere.
    Admin-only + tightly rate limited; this is the only endpoint that outputs it."""
    target = _resolve_user(req.user_id)
    conn = simplefin_service.get_connection(target["name"])
    if not conn:
        raise HTTPException(status_code=404, detail="No connection for that user")
    return {"access_url": conn["access_url"]}


@router.delete("/simplefin/{user_id}")
def disconnect_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    target = _resolve_user(user_id)
    if not simplefin_service.disconnect(target["name"]):
        raise HTTPException(status_code=404, detail="No connection for that user")
    return {"ok": True}


@router.post("/simplefin/sync")
def sync_now(
    req: UserRef,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_sync_limit),
):
    target = _resolve_user(req.user_id)
    if not simplefin_path(target["name"]).exists():
        raise HTTPException(status_code=404, detail="No connection for that user")
    result = simplefin_service.sync_user(target["name"])
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# CSV import (edit access on the target book)
# ---------------------------------------------------------------------------


@router.post("/books/{book_id}/import/csv")
async def csv_preview(
    book_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _store, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    content = await file.read()
    try:
        return finance_import_service.preview_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/books/{book_id}/import/csv/commit")
async def csv_commit(
    book_id: str,
    file: UploadFile = File(...),
    account_id: str = Form(...),
    date_col: str = Form(...),
    amount_col: str = Form(...),
    payee_col: str = Form(default=""),
    notes_col: str = Form(default=""),
    date_format: str = Form(default=""),
    invert_amounts: bool = Form(default=False),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    content = await file.read()
    mapping = {
        "account_id": account_id,
        "date_col": date_col,
        "amount_col": amount_col,
        "payee_col": payee_col or None,
        "notes_col": notes_col or None,
        "date_format": date_format or None,
        "invert_amounts": invert_amounts,
    }
    try:
        return finance_import_service.commit_csv(
            store_user, workspace, book, content, mapping, created_by=current_user["name"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Payee → category rules
# ---------------------------------------------------------------------------


@router.get("/books/{book_id}/rules")
def list_rules(
    book_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    return finance_service.list_rules(store_user, workspace, book_id)


@router.delete("/books/{book_id}/rules/{rule_id}")
def delete_rule(
    book_id: str,
    rule_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    if not finance_service.delete_rule(store_user, workspace, book_id, rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"ok": True}
