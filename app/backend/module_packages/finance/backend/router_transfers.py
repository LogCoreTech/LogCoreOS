"""Finance transfers: a linked pair of transactions moving money between two
accounts — same book or two different books, same or different workspace.

Each leg is an ordinary transaction in its own book (so it appears in that
book's own transaction list "like it should"), tagged with a shared
transfer_pair_id and denormalized peer info so it never needs a cross-book
lookup to render itself. Both books must share a currency (no FX conversion —
matches the precedent finance_reports.net_worth() already set); books may be
in different workspaces (personal <-> business allowed, per owner decision).
Editing/deleting a transfer always touches both legs together through this
router — the existing single-transaction endpoints in finance.py reject any
attempt to edit or delete one leg directly (see _reject_transfer_leg there).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from module_packages.finance.backend.router import _find_or_404, _require_edit
from routers.auth import require_module
from services import finance_service
from services.rate_limiter import rate_limit

_require_finance = require_module("finance")
_write_limit = rate_limit(30, 60)

router = APIRouter()

_WS_PATTERN = "^(personal|business)$"


class TransferCreate(BaseModel):
    from_book_id: str
    from_workspace: str = Field(..., pattern=_WS_PATTERN)
    from_account_id: str
    to_book_id: str
    to_workspace: str = Field(..., pattern=_WS_PATTERN)
    to_account_id: str
    amount_cents: int = Field(..., gt=0)
    date: str
    notes: str = Field(default="", max_length=2000)


class TransferUpdate(BaseModel):
    from_book_id: str
    from_workspace: str = Field(..., pattern=_WS_PATTERN)
    to_book_id: str
    to_workspace: str = Field(..., pattern=_WS_PATTERN)
    amount_cents: int | None = Field(default=None, gt=0)
    date: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


def _entitled(user: dict, workspace: str) -> None:
    if workspace not in (user.get("workspaces") or ["personal"]):
        raise HTTPException(
            status_code=403, detail=f"You don't have access to the {workspace} workspace."
        )


def _resolve_edit(user: dict, workspace: str, book_id: str) -> tuple[str, dict]:
    _entitled(user, workspace)
    store_user, book, access = _find_or_404(user, workspace, book_id)
    _require_edit(access)
    return store_user, book


def _account_name(book: dict, account_id: str) -> str:
    account = next((a for a in book.get("accounts", []) if a["id"] == account_id), None)
    return account["name"] if account else ""


@router.post("/transfers", status_code=201)
def create_transfer(
    req: TransferCreate,
    current_user: dict = Depends(_require_finance),
    _rl: None = Depends(_write_limit),
):
    if req.from_book_id == req.to_book_id and req.from_account_id == req.to_account_id:
        raise HTTPException(
            status_code=400, detail="Pick two different accounts to transfer between."
        )
    from_store, from_book = _resolve_edit(current_user, req.from_workspace, req.from_book_id)
    to_store, to_book = _resolve_edit(current_user, req.to_workspace, req.to_book_id)
    if from_book.get("currency", "USD") != to_book.get("currency", "USD"):
        raise HTTPException(status_code=400, detail="Both books must use the same currency.")

    pair_id = str(uuid.uuid4())
    try:
        from_tx = finance_service.add_transaction(
            from_store,
            req.from_workspace,
            from_book,
            {
                "date": req.date,
                "amount_cents": -req.amount_cents,
                "account_id": req.from_account_id,
                "notes": req.notes,
                "transfer_pair_id": pair_id,
                "transfer_peer_book_id": req.to_book_id,
                "transfer_peer_book_name": to_book["name"],
                "transfer_peer_workspace": req.to_workspace,
                "transfer_peer_account_id": req.to_account_id,
                "transfer_peer_account_name": _account_name(to_book, req.to_account_id),
            },
            created_by=current_user["name"],
            source="transfer",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        to_tx = finance_service.add_transaction(
            to_store,
            req.to_workspace,
            to_book,
            {
                "date": req.date,
                "amount_cents": req.amount_cents,
                "account_id": req.to_account_id,
                "notes": req.notes,
                "transfer_pair_id": pair_id,
                "transfer_peer_book_id": req.from_book_id,
                "transfer_peer_book_name": from_book["name"],
                "transfer_peer_workspace": req.from_workspace,
                "transfer_peer_account_id": req.from_account_id,
                "transfer_peer_account_name": _account_name(from_book, req.from_account_id),
            },
            created_by=current_user["name"],
            source="transfer",
        )
    except ValueError as exc:
        # Best-effort cleanup — a mid-transfer failure shouldn't leave an
        # orphaned leg permanently excluded from reports with no counterpart.
        finance_service.delete_transaction(
            from_store, req.from_workspace, from_book["id"], from_tx["id"]
        )
        raise HTTPException(status_code=400, detail=str(exc))

    # Deliberately skips finance_planning_service.on_transactions_added() (bill
    # matching + budget alerts) — match_bill() is category-blind (account +
    # sign + amount tolerance + date tolerance only), so a transfer leg could
    # otherwise coincidentally false-match an unrelated recurring bill.
    return {"from": from_tx, "to": to_tx}


@router.patch("/transfers/{transfer_pair_id}")
def update_transfer(
    transfer_pair_id: str,
    req: TransferUpdate,
    current_user: dict = Depends(_require_finance),
    _rl: None = Depends(_write_limit),
):
    """Amount/date/notes only — both legs move together. Changing which books
    or accounts are involved isn't supported here; delete and recreate."""
    from_store, from_book = _resolve_edit(current_user, req.from_workspace, req.from_book_id)
    to_store, to_book = _resolve_edit(current_user, req.to_workspace, req.to_book_id)

    from_tx = finance_service.get_transaction_by_transfer_pair(
        from_store, req.from_workspace, from_book["id"], transfer_pair_id, negative=True
    )
    to_tx = finance_service.get_transaction_by_transfer_pair(
        to_store, req.to_workspace, to_book["id"], transfer_pair_id, negative=False
    )
    if not from_tx or not to_tx:
        raise HTTPException(status_code=404, detail="Transfer not found")

    updates = req.model_dump(
        exclude_unset=True,
        exclude={"from_book_id", "from_workspace", "to_book_id", "to_workspace"},
    )
    if not updates:
        return {"from": from_tx, "to": to_tx}

    from_updates = dict(updates)
    if "amount_cents" in from_updates:
        from_updates["amount_cents"] = -from_updates["amount_cents"]
    try:
        from_result = finance_service.update_transaction(
            from_store, req.from_workspace, from_book, from_tx["id"], from_updates
        )
        to_result = finance_service.update_transaction(
            to_store, req.to_workspace, to_book, to_tx["id"], updates
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"from": from_result, "to": to_result}


@router.delete("/transfers/{transfer_pair_id}")
def delete_transfer(
    transfer_pair_id: str,
    from_book_id: str = Query(...),
    from_workspace: str = Query(..., pattern=_WS_PATTERN),
    to_book_id: str = Query(...),
    to_workspace: str = Query(..., pattern=_WS_PATTERN),
    current_user: dict = Depends(_require_finance),
    _rl: None = Depends(_write_limit),
):
    from_store, from_book = _resolve_edit(current_user, from_workspace, from_book_id)
    to_store, to_book = _resolve_edit(current_user, to_workspace, to_book_id)

    from_tx = finance_service.get_transaction_by_transfer_pair(
        from_store, from_workspace, from_book["id"], transfer_pair_id, negative=True
    )
    to_tx = finance_service.get_transaction_by_transfer_pair(
        to_store, to_workspace, to_book["id"], transfer_pair_id, negative=False
    )
    if not from_tx and not to_tx:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if from_tx:
        finance_service.delete_transaction(
            from_store, from_workspace, from_book["id"], from_tx["id"]
        )
    if to_tx:
        finance_service.delete_transaction(to_store, to_workspace, to_book["id"], to_tx["id"])
    return {"ok": True}
