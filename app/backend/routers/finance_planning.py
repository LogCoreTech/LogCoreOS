"""Finance planning endpoints: budgets, recurring bills, planned items, projection."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routers.auth import get_workspace, require_module
from routers.finance import _find_or_404, _require_edit, _require_full_read
from services import finance_planning_service as planning
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


class BudgetEntry(BaseModel):
    category: str = Field(..., min_length=1, max_length=40)
    monthly_limit_cents: int = Field(..., gt=0)


class BudgetsRequest(BaseModel):
    budgets: list[BudgetEntry] = Field(default_factory=list, max_length=100)


class RecurringCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    amount_cents: int
    account_id: str
    category: str = Field(default="", max_length=40)
    cadence: str = Field(default="monthly", pattern="^(weekly|monthly|yearly)$")
    next_due: str
    autopay: bool = False


class RecurringUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    amount_cents: int | None = None
    account_id: str | None = None
    category: str | None = Field(default=None, max_length=40)
    cadence: str | None = Field(default=None, pattern="^(weekly|monthly|yearly)$")
    next_due: str | None = None
    autopay: bool | None = None
    active: bool | None = None


class PlannedCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    date: str
    amount_cents: int
    account_id: str


class PlannedUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    date: str | None = None
    amount_cents: int | None = None
    account_id: str | None = None
    done: bool | None = None


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


@router.get("/books/{book_id}/budgets")
def get_budgets(
    book_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, book, _access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, book, _access)
    return planning.get_budgets(store_user, workspace, book_id).get("budgets", [])


@router.put("/books/{book_id}/budgets")
def set_budgets(
    book_id: str,
    req: BudgetsRequest,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    try:
        return planning.set_budgets(
            store_user, workspace, book, [b.model_dump() for b in req.budgets]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/books/{book_id}/budgets/status")
def budgets_status(
    book_id: str,
    month: str = Query(..., min_length=7, max_length=7),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, book, _access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, book, _access)
    return planning.budget_status(store_user, workspace, book, month)


# ---------------------------------------------------------------------------
# Recurring
# ---------------------------------------------------------------------------


@router.get("/books/{book_id}/recurring")
def list_recurring(
    book_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, _book, _access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, _book, _access)
    return planning.list_recurring(store_user, workspace, book_id)


@router.get("/books/{book_id}/recurring/upcoming")
def upcoming_recurring(
    book_id: str,
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, _book, _access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, _book, _access)
    return planning.upcoming_recurring(store_user, workspace, book_id, days)


@router.post("/books/{book_id}/recurring", status_code=201)
def add_recurring(
    book_id: str,
    req: RecurringCreate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    try:
        return planning.add_recurring(
            store_user, workspace, book, req.model_dump(), created_by=current_user["name"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/books/{book_id}/recurring/{item_id}")
def update_recurring(
    book_id: str,
    item_id: str,
    req: RecurringUpdate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_uuid(item_id, "item ID")
    try:
        result = planning.update_recurring(
            store_user, workspace, book, item_id, req.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="Recurring item not found")
    return result


@router.delete("/books/{book_id}/recurring/{item_id}")
def delete_recurring(
    book_id: str,
    item_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_uuid(item_id, "item ID")
    if not planning.delete_recurring(store_user, workspace, book_id, item_id):
        raise HTTPException(status_code=404, detail="Recurring item not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Planned one-offs
# ---------------------------------------------------------------------------


@router.get("/books/{book_id}/planned")
def list_planned(
    book_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, _book, _access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, _book, _access)
    return planning.list_planned(store_user, workspace, book_id)


@router.post("/books/{book_id}/planned", status_code=201)
def add_planned(
    book_id: str,
    req: PlannedCreate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    try:
        return planning.add_planned(
            store_user, workspace, book, req.model_dump(), created_by=current_user["name"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/books/{book_id}/planned/{item_id}")
def update_planned(
    book_id: str,
    item_id: str,
    req: PlannedUpdate,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_uuid(item_id, "item ID")
    try:
        result = planning.update_planned(
            store_user, workspace, book, item_id, req.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="Planned item not found")
    return result


@router.delete("/books/{book_id}/planned/{item_id}")
def delete_planned(
    book_id: str,
    item_id: str,
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _book, access = _find_or_404(current_user, workspace, book_id)
    _require_edit(access)
    _validate_uuid(item_id, "item ID")
    if not planning.delete_planned(store_user, workspace, book_id, item_id):
        raise HTTPException(status_code=404, detail="Planned item not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


@router.get("/books/{book_id}/accounts/{account_id}/projection")
def projection(
    book_id: str,
    account_id: str,
    date: str = Query(..., min_length=10, max_length=10),
    current_user: dict = Depends(_require_finance),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, book, _access = _find_or_404(current_user, workspace, book_id)
    _require_full_read(current_user, workspace, store_user, book, _access)
    _validate_uuid(account_id, "account ID")
    try:
        return planning.project_balance(store_user, workspace, book, account_id, date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
