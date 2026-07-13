"""Finance module: books, accounts, transactions, reports, net worth.

Every path resolves access through finance_service.find_book() /
_resolve_book_access() — access is never decided in the frontend.
Pool books (household/team) are workspace-visible; writes are admin-only
until per-book contributors land in the sharing phase.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from routers.auth import get_workspace, require_module
from services import finance_reports, finance_service
from services.rate_limiter import rate_limit

_require_finance = require_module("finance")
_read_limit = rate_limit(60, 60)
_write_limit = rate_limit(30, 60)

router = APIRouter()


def _validate_id(value: str, label: str = "ID") -> str:
    try:
        UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label} format")
    return value


def _find_or_404(user: dict, workspace: str, book_id: str) -> tuple[str, dict, str]:
    _validate_id(book_id, "book ID")
    found = finance_service.find_book(
        user["name"],
        user.get("feature_role", "member"),
        user.get("role") == "admin",
        workspace,
        book_id,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Book not found")
    return found


def _require_edit(access: str) -> None:
    if access != "edit":
        raise HTTPException(
            status_code=403, detail="You don't have permission to make changes here."
        )


def _caps_for(
    user: dict, workspace: str, store_user: str, book: dict, account_id: str | None = None
) -> dict | None:
    """Contribute caps for the current viewer (None for read/edit/owner)."""
    return finance_service.resolve_caps(
        user["name"],
        user.get("feature_role", "member"),
        user.get("role") == "admin",
        store_user,
        book,
        account_id,
        workspace,
    )


def _require_full_read(user: dict, workspace: str, store_user: str, book: dict, access: str):
    """Contribute viewers without the see_balances cap cannot read money
    summaries (reports, budgets, projections, invoices)."""
    if access != "contribute":
        return
    caps = _caps_for(user, workspace, store_user, book)
    if not (caps or {}).get("see_balances"):
        raise HTTPException(
            status_code=403, detail="You don't have permission to view balances here."
        )


def _require_contribute_own_tx(
    user: dict, workspace: str, store_user: str, book: dict, tx_id: str, req
) -> None:
    """Contribute-level writes touch only the viewer's own transactions, need the
    edit_own cap, and any amount change must keep an allowed sign."""
    caps = _caps_for(user, workspace, store_user, book) or {}
    if not caps.get("edit_own"):
        raise HTTPException(status_code=403, detail="Your access doesn't allow editing entries.")
    tx = finance_service.get_transaction(store_user, workspace, book["id"], tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if tx.get("created_by") != user["name"]:
        raise HTTPException(status_code=403, detail="You can only change entries you created.")
    new_amount = getattr(req, "amount_cents", None) if req is not None else None
    if new_amount is not None:
        kind = "income" if new_amount > 0 else "expense"
        if kind not in caps.get("add", []):
            raise HTTPException(
                status_code=403, detail=f"Your access doesn't allow {kind} entries."
            )


def _strip_balances(book_out: dict) -> dict:
    """Server-side field stripping for contribute viewers without see_balances —
    never render-only."""
    out = dict(book_out)
    out.pop("balances", None)
    out.pop("total_cents", None)
    out["accounts"] = [
        {
            k: v
            for k, v in account.items()
            if k not in ("opening_balance_cents", "synced_balance_cents")
        }
        for account in out.get("accounts", [])
    ]
    return out


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CategoryModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    kind: Literal["expense", "income"] = "expense"


class BookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    icon: str = Field(default="", max_length=8)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    categories: list[CategoryModel] | None = None
    pool: bool = False


class BookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    icon: str | None = Field(default=None, max_length=8)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    budget_warn_pct: int | None = Field(default=None, ge=1, le=100)
    archived: bool | None = None
    categories: list[CategoryModel] | None = None
    tax_categories: list[str] | None = None


class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    type: Literal["checking", "savings", "credit", "cash", "other"] = "checking"
    opening_balance_cents: int = 0
    opening_date: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    type: Literal["checking", "savings", "credit", "cash", "other"] | None = None
    opening_balance_cents: int | None = None
    opening_date: str | None = None
    deviation_threshold_cents: int | None = None
    archived: bool | None = None
    # Manual "actual balance" entry — enables deviation checks on accounts
    # without a bank feed (cash). Bank sync overwrites it on each pull.
    synced_balance_cents: int | None = None


class TransactionCreate(BaseModel):
    date: str
    amount_cents: int
    account_id: str
    category: str = Field(default="", max_length=40)
    payee: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)
    deductible: bool = False
    tax_category: str | None = Field(default=None, max_length=60)


class TransactionUpdate(BaseModel):
    date: str | None = None
    amount_cents: int | None = None
    account_id: str | None = None
    category: str | None = Field(default=None, max_length=40)
    payee: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    deductible: bool | None = None
    tax_category: str | None = Field(default=None, max_length=60)


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------


@router.get("/books")
def list_books(
    include_archived: bool = Query(default=False),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    viewer = current_user["name"]
    books = finance_service.list_visible_books(
        viewer,
        current_user.get("feature_role", "member"),
        current_user.get("role") == "admin",
        workspace,
        include_archived=include_archived,
    )
    out = []
    for book in books:
        store_user = finance_service.store_for_annotated(book, viewer, workspace)
        if book.get("_access") == "contribute" and not (book.get("_caps") or {}).get(
            "see_balances"
        ):
            out.append(_strip_balances(book))
            continue
        summary = finance_service.book_summary(store_user, workspace, book)
        book["balances"] = summary["balances"]
        book["total_cents"] = summary["total_cents"]
        out.append(book)
    return out


@router.post("/books", status_code=201)
def create_book(
    req: BookCreate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    if req.pool:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins can create pool books")
        store_user = finance_service.pool_for(workspace)
    else:
        store_user = current_user["name"]
    try:
        book = finance_service.create_book(
            store_user,
            workspace,
            name=req.name,
            created_by=current_user["name"],
            icon=req.icon,
            currency=req.currency,
            categories=[c.model_dump() for c in req.categories] if req.categories else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return finance_service.annotate(book, store_user, current_user["name"], "edit")


@router.get("/books/{book_id}")
def get_book(
    book_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    caps = _caps_for(current_user, workspace, store_user, book) if access == "contribute" else None
    out = finance_service.annotate(book, store_user, current_user["name"], access, caps)
    if access == "contribute" and not (caps or {}).get("see_balances"):
        return _strip_balances(out)
    summary = finance_service.book_summary(store_user, workspace, book)
    out["balances"] = summary["balances"]
    out["total_cents"] = summary["total_cents"]
    return out


@router.patch("/books/{book_id}")
def update_book(
    book_id: str,
    req: BookUpdate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    updates = req.model_dump(exclude_unset=True)
    if "categories" in updates and updates["categories"] is not None:
        updates["categories"] = [dict(c) for c in updates["categories"]]
    try:
        result = finance_service.update_book(store_user, workspace, book_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="Book not found")
    return finance_service.annotate(result, store_user, current_user["name"], access)


@router.delete("/books/{book_id}")
def delete_book(
    book_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    # Hard delete: own books only for their owner; pool books admin-only.
    # (Edit-shared users gain "edit" in the sharing phase but never delete.)
    is_admin = current_user.get("role") == "admin"
    if finance_service.is_pool(store_user):
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only admins can delete pool books")
    elif store_user != current_user["name"]:
        raise HTTPException(status_code=403, detail="Only the owner can delete this book")
    if finance_service.has_transactions(store_user, workspace, book_id):
        raise HTTPException(
            status_code=409,
            detail="Book still has transactions — archive it instead, or delete them first.",
        )
    finance_service.delete_book(store_user, workspace, book_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


@router.post("/books/{book_id}/accounts", status_code=201)
def add_account(
    book_id: str,
    req: AccountCreate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    try:
        account = finance_service.add_account(store_user, workspace, book_id, req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not account:
        raise HTTPException(status_code=404, detail="Book not found")
    return account


@router.patch("/books/{book_id}/accounts/{account_id}")
def update_account(
    book_id: str,
    account_id: str,
    req: AccountUpdate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_id(account_id, "account ID")
    try:
        account = finance_service.update_account(
            store_user, workspace, book_id, account_id, req.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.delete("/books/{book_id}/accounts/{account_id}")
def delete_account(
    book_id: str,
    account_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_id(account_id, "account ID")
    if finance_service.account_has_transactions(store_user, workspace, book_id, account_id):
        raise HTTPException(
            status_code=409,
            detail="Account still has transactions — archive it instead.",
        )
    if not finance_service.delete_account(store_user, workspace, book_id, account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


@router.get("/books/{book_id}/transactions")
def list_transactions(
    book_id: str,
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    account: str | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    created_by_filter = None
    if access == "contribute":
        caps = _caps_for(current_user, workspace, store_user, book, account)
        if not (caps or {}).get("see_all_tx"):
            created_by_filter = current_user["name"]  # own entries only
    try:
        items, total = finance_service.list_transactions(
            store_user,
            workspace,
            book_id,
            date_from=date_from,
            date_to=date_to,
            account_id=account,
            category=category,
            query=q,
            created_by=created_by_filter,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"items": items, "total": total}


@router.post("/books/{book_id}/transactions", status_code=201)
def add_transaction(
    book_id: str,
    req: TransactionCreate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    if access == "contribute":
        caps = _caps_for(current_user, workspace, store_user, book, req.account_id) or {}
        kind = "income" if req.amount_cents > 0 else "expense"
        if kind not in caps.get("add", []):
            raise HTTPException(
                status_code=403, detail=f"Your access doesn't allow adding {kind} entries."
            )
    else:
        _require_edit(access)
    try:
        tx = finance_service.add_transaction(
            store_user, workspace, book, req.model_dump(), created_by=current_user["name"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    from services import finance_planning_service

    finance_planning_service.on_transactions_added(store_user, workspace, book_id, [tx])
    return tx


@router.patch("/books/{book_id}/transactions/{tx_id}")
def update_transaction(
    book_id: str,
    tx_id: str,
    req: TransactionUpdate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _validate_id(tx_id, "transaction ID")
    if access == "contribute":
        _require_contribute_own_tx(current_user, workspace, store_user, book, tx_id, req)
    else:
        _require_edit(access)
    try:
        updates = req.model_dump(exclude_unset=True)
        result = finance_service.update_transaction(store_user, workspace, book, tx_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="Transaction not found")
    # Learn payee→category rules from the user categorizing imported transactions,
    # so the next bank sync / CSV import auto-categorizes the same payee.
    if (
        updates.get("category")
        and result.get("payee")
        and result.get("source") in ("simplefin", "csv")
    ):
        finance_service.learn_rule(
            store_user, workspace, book_id, result["payee"], result["category"]
        )
    return result


@router.delete("/books/{book_id}/transactions/{tx_id}")
def delete_transaction(
    book_id: str,
    tx_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _validate_id(tx_id, "transaction ID")
    if access == "contribute":
        _require_contribute_own_tx(current_user, workspace, store_user, book, tx_id, None)
    else:
        _require_edit(access)
    if not finance_service.delete_transaction(store_user, workspace, book_id, tx_id):
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Receipts (photo/PDF attachments on transactions)
# ---------------------------------------------------------------------------


@router.post("/books/{book_id}/transactions/{tx_id}/receipts", status_code=201)
async def upload_receipt(
    book_id: str,
    tx_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_id(tx_id, "transaction ID")
    if file.content_type not in finance_service.RECEIPT_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG/PNG/WebP/AVIF images and PDFs")
    content = await file.read()
    try:
        return finance_service.add_receipt(
            store_user,
            workspace,
            book_id,
            tx_id,
            file.filename or "receipt",
            file.content_type,
            content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/books/{book_id}/transactions/{tx_id}/receipts/{receipt_id}")
def download_receipt(
    book_id: str,
    tx_id: str,
    receipt_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _validate_id(tx_id, "transaction ID")
    _validate_id(receipt_id, "receipt ID")
    found = finance_service.get_receipt(store_user, workspace, book_id, tx_id, receipt_id)
    if not found:
        raise HTTPException(status_code=404, detail="Receipt not found")
    path, mime, filename = found
    return FileResponse(str(path), media_type=mime, filename=filename)


@router.delete("/books/{book_id}/transactions/{tx_id}/receipts/{receipt_id}", status_code=204)
def delete_receipt(
    book_id: str,
    tx_id: str,
    receipt_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_id(tx_id, "transaction ID")
    _validate_id(receipt_id, "receipt ID")
    if not finance_service.delete_receipt(store_user, workspace, book_id, tx_id, receipt_id):
        raise HTTPException(status_code=404, detail="Receipt not found")


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@router.get("/books/{book_id}/reports/monthly")
def monthly_report(
    book_id: str,
    month: str = Query(..., min_length=7, max_length=7),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, book, access)
    try:
        return finance_reports.monthly_report(store_user, workspace, book, month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/books/{book_id}/reports/pnl")
def pnl_report(
    book_id: str,
    year: int = Query(..., ge=2000, le=2100),
    period: Literal["year", "quarter", "month"] = Query(default="year"),
    quarter: int | None = Query(default=None, ge=1, le=4),
    month: int | None = Query(default=None, ge=1, le=12),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, book, access)
    try:
        return finance_reports.pnl(
            store_user, workspace, book, year, period=period, quarter=quarter, month=month
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/books/{book_id}/reports/tax")
def tax_report(
    book_id: str,
    year: int = Query(..., ge=2000, le=2100),
    format: Literal["json", "csv"] = Query(default="json"),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, book, access)
    if format == "csv":
        csv_text = finance_reports.tax_summary_csv(store_user, workspace, book, year)
        return PlainTextResponse(
            csv_text,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="tax_{year}_{book["name"]}.csv"'
            },
        )
    return finance_reports.tax_summary(store_user, workspace, book, year)


@router.get("/networth")
def net_worth(
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    return finance_reports.net_worth(
        current_user["name"],
        current_user.get("feature_role", "member"),
        current_user.get("role") == "admin",
        workspace,
    )
