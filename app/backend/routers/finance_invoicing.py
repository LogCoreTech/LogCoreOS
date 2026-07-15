"""Finance invoicing endpoints: clients, invoices, payments, AR rollup."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_workspace, require_module
from routers.finance import _find_or_404, _require_edit, _require_full_read
from services import finance_invoice_service as invoicing
from services.rate_limiter import rate_limit

_require_finance = require_module("finance")
_read_limit = rate_limit(60, 60)
_write_limit = rate_limit(30, 60)

router = APIRouter()


def _validate_uuid(value: str, label: str) -> str:
    try:
        UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label} format")
    return value


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=2000)
    contact_id: str | None = Field(default=None, max_length=64)


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)
    contact_id: str | None = Field(default=None, max_length=64)
    archived: bool | None = None


class LineItem(BaseModel):
    description: str = Field(..., min_length=1, max_length=200)
    qty: float = Field(default=1, gt=0, le=100000)
    unit_cents: int


class InvoiceCreate(BaseModel):
    client_id: str | None = None
    issue_date: str | None = None
    due_date: str
    line_items: list[LineItem] = Field(..., min_length=1, max_length=50)
    tax_pct: float = Field(default=0, ge=0, le=50)
    notes: str = Field(default="", max_length=2000)


class InvoiceUpdate(BaseModel):
    client_id: str | None = None
    status: str | None = Field(default=None, pattern="^(draft|sent|paid|void)$")
    issue_date: str | None = None
    due_date: str | None = None
    line_items: list[LineItem] | None = Field(default=None, min_length=1, max_length=50)
    tax_pct: float | None = Field(default=None, ge=0, le=50)
    notes: str | None = Field(default=None, max_length=2000)


class PaymentCreate(BaseModel):
    amount_cents: int = Field(..., gt=0)
    date: str | None = None
    method: str = Field(default="", max_length=40)
    # When set, an income transaction is created in this account and linked
    account_id: str | None = None
    category: str = Field(default="", max_length=40)


# ---------------------------------------------------------------------------
# Clients + AR
# ---------------------------------------------------------------------------


@router.get("/books/{book_id}/clients")
def list_clients(
    book_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, _book, _access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, _book, _access)
    return invoicing.list_clients(store_user, workspace, book_id)


@router.post("/books/{book_id}/clients", status_code=201)
def add_client(
    book_id: str,
    req: ClientCreate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    try:
        return invoicing.add_client(
            store_user, workspace, book_id, req.model_dump(), created_by=current_user["name"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/books/{book_id}/clients/{client_id}")
def update_client(
    book_id: str,
    client_id: str,
    req: ClientUpdate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_uuid(client_id, "client ID")
    try:
        result = invoicing.update_client(
            store_user, workspace, book_id, client_id, req.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="Client not found")
    return result


@router.delete("/books/{book_id}/clients/{client_id}")
def delete_client(
    book_id: str,
    client_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_uuid(client_id, "client ID")
    if invoicing.client_has_invoices(store_user, workspace, book_id, client_id):
        raise HTTPException(
            status_code=409, detail="Client has invoices — archive them instead of deleting."
        )
    if not invoicing.delete_client(store_user, workspace, book_id, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    return {"ok": True}


@router.get("/books/{book_id}/clients/ar")
def ar_rollup(
    book_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, _book, _access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, _book, _access)
    return invoicing.ar_summary(store_user, workspace, book_id)


# ---------------------------------------------------------------------------
# Invoices + payments
# ---------------------------------------------------------------------------


@router.get("/books/{book_id}/invoices")
def list_invoices(
    book_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, _book, _access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, _book, _access)
    return invoicing.list_invoices(store_user, workspace, book_id)


@router.post("/books/{book_id}/invoices", status_code=201)
def create_invoice(
    book_id: str,
    req: InvoiceCreate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    try:
        return invoicing.create_invoice(
            store_user, workspace, book_id, req.model_dump(), created_by=current_user["name"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/books/{book_id}/invoices/{invoice_id}")
def get_invoice(
    book_id: str,
    invoice_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, _book, _access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, _book, _access)
    _validate_uuid(invoice_id, "invoice ID")
    invoice = invoicing.get_invoice(store_user, workspace, book_id, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.patch("/books/{book_id}/invoices/{invoice_id}")
def update_invoice(
    book_id: str,
    invoice_id: str,
    req: InvoiceUpdate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_uuid(invoice_id, "invoice ID")
    try:
        result = invoicing.update_invoice(
            store_user, workspace, book_id, invoice_id, req.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return result


@router.delete("/books/{book_id}/invoices/{invoice_id}")
def delete_invoice(
    book_id: str,
    invoice_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_uuid(invoice_id, "invoice ID")
    if not invoicing.delete_invoice(store_user, workspace, book_id, invoice_id):
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"ok": True}


@router.post("/books/{book_id}/invoices/{invoice_id}/payments", status_code=201)
def record_payment(
    book_id: str,
    invoice_id: str,
    req: PaymentCreate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_uuid(invoice_id, "invoice ID")
    try:
        result = invoicing.record_payment(
            store_user,
            workspace,
            book_id,
            invoice_id,
            req.model_dump(),
            created_by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return result


@router.delete("/books/{book_id}/invoices/{invoice_id}/payments/{payment_id}")
def delete_payment(
    book_id: str,
    invoice_id: str,
    payment_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_uuid(invoice_id, "invoice ID")
    _validate_uuid(payment_id, "payment ID")
    result = invoicing.delete_payment(store_user, workspace, book_id, invoice_id, payment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Payment not found")
    return result
