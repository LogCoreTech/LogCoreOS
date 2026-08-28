"""Finance Transfers: a linked pair of transactions moving money between two
accounts, same book or cross-book, same or cross-workspace (owner explicitly
chose to allow personal <-> business). Router functions are imported and
called directly (mirrors test_simplefin_pool.py/test_features.py) since the
workspace-entitlement + currency-match logic lives in
routers/finance_transfers.py itself, not in finance_service.py.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.finance.backend.router import TransactionUpdate
from module_packages.finance.backend.router import delete_transaction as single_tx_delete
from module_packages.finance.backend.router import update_transaction as single_tx_update
from module_packages.finance.backend.router_transfers import (
    TransferCreate,
    TransferUpdate,
    create_transfer,
    delete_transfer,
    update_transfer,
)
from services import auth_service
from services import finance_planning_service as planning
from module_packages.finance.backend import reports
from services import finance_service as fin


@pytest.fixture()
def owner(brain):
    user = auth_service.create_user("owner@example.com", "password123", "Owner", role="admin")
    return {**user, "workspaces": ["personal", "business"]}


@pytest.fixture()
def personal_only(brain):
    user = auth_service.create_user("member@example.com", "password123", "Member", role="member")
    return {**user, "workspaces": ["personal"]}


@pytest.fixture()
def personal_book(brain, owner):
    book = fin.create_book("Owner", "personal", name="Household", created_by="Owner")
    fin.add_account(
        "Owner",
        "personal",
        book["id"],
        {"name": "Checking", "type": "checking", "opening_balance_cents": 100_000},
    )
    return fin.get_book("Owner", "personal", book["id"])


@pytest.fixture()
def business_book(brain, owner):
    book = fin.create_book("Owner", "business", name="Client Ops", created_by="Owner")
    fin.add_account(
        "Owner",
        "business",
        book["id"],
        {"name": "Operating", "type": "checking", "opening_balance_cents": 50_000},
    )
    return fin.get_book("Owner", "business", book["id"])


def _acct(book):
    return book["accounts"][0]["id"]


def test_cross_workspace_transfer_creates_both_legs_correctly(owner, personal_book, business_book):
    result = create_transfer(
        TransferCreate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            from_account_id=_acct(personal_book),
            to_book_id=business_book["id"],
            to_workspace="business",
            to_account_id=_acct(business_book),
            amount_cents=10_000,
            date="2026-08-14",
            notes="Owner injecting capital",
        ),
        owner,
    )
    from_tx, to_tx = result["from"], result["to"]

    assert from_tx["amount_cents"] == -10_000
    assert to_tx["amount_cents"] == 10_000
    assert from_tx["transfer_pair_id"] == to_tx["transfer_pair_id"]
    assert from_tx["transfer_peer_book_id"] == business_book["id"]
    assert from_tx["transfer_peer_workspace"] == "business"
    assert from_tx["transfer_peer_account_name"] == "Operating"
    assert to_tx["transfer_peer_book_id"] == personal_book["id"]
    assert to_tx["transfer_peer_workspace"] == "personal"
    assert to_tx["transfer_peer_account_name"] == "Checking"

    # Balances net correctly on both sides, in both workspaces.
    personal_balances = fin.account_balances(
        "Owner", "personal", fin.get_book("Owner", "personal", personal_book["id"])
    )
    business_balances = fin.account_balances(
        "Owner", "business", fin.get_book("Owner", "business", business_book["id"])
    )
    assert personal_balances[_acct(personal_book)] == 100_000 - 10_000
    assert business_balances[_acct(business_book)] == 50_000 + 10_000


def test_same_book_transfer_is_the_degenerate_case(owner, personal_book):
    fin.add_account(
        "Owner", "personal", personal_book["id"], {"name": "Savings", "type": "savings"}
    )
    fresh = fin.get_book("Owner", "personal", personal_book["id"])
    savings_id = next(a["id"] for a in fresh["accounts"] if a["name"] == "Savings")

    result = create_transfer(
        TransferCreate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            from_account_id=_acct(personal_book),
            to_book_id=personal_book["id"],
            to_workspace="personal",
            to_account_id=savings_id,
            amount_cents=5_000,
            date="2026-08-14",
        ),
        owner,
    )
    assert result["from"]["transfer_peer_book_id"] == personal_book["id"]


def test_same_book_transfer_delete_removes_both_legs(owner, personal_book):
    """Regression for a real bug (2026-08-15): get_transaction_by_transfer_pair
    matched on transfer_pair_id alone, so looking it up twice for a same-book
    transfer (both legs share one store/workspace/book) returned the SAME
    transaction both times — delete_transfer then deleted the "from" leg,
    tried to delete it again for "to" (no-op, already gone), and the real
    "to" leg silently survived. Fixed by disambiguating on amount sign."""
    fin.add_account(
        "Owner", "personal", personal_book["id"], {"name": "Savings", "type": "savings"}
    )
    fresh = fin.get_book("Owner", "personal", personal_book["id"])
    savings_id = next(a["id"] for a in fresh["accounts"] if a["name"] == "Savings")

    created = create_transfer(
        TransferCreate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            from_account_id=_acct(personal_book),
            to_book_id=personal_book["id"],
            to_workspace="personal",
            to_account_id=savings_id,
            amount_cents=5_000,
            date="2026-08-15",
        ),
        owner,
    )
    pair_id = created["from"]["transfer_pair_id"]
    assert created["from"]["id"] != created["to"]["id"]

    delete_transfer(
        pair_id,
        from_book_id=personal_book["id"],
        from_workspace="personal",
        to_book_id=personal_book["id"],
        to_workspace="personal",
        current_user=owner,
    )
    assert (
        fin.get_transaction("Owner", "personal", personal_book["id"], created["from"]["id"]) is None
    )
    assert (
        fin.get_transaction("Owner", "personal", personal_book["id"], created["to"]["id"]) is None
    )


def test_same_book_transfer_update_moves_both_legs(owner, personal_book):
    """Same disambiguation bug as the delete case above, but for update: an
    unfixed version would apply the "to" update on top of the "from" leg
    twice, leaving one real leg untouched and stale."""
    fin.add_account(
        "Owner", "personal", personal_book["id"], {"name": "Savings", "type": "savings"}
    )
    fresh = fin.get_book("Owner", "personal", personal_book["id"])
    savings_id = next(a["id"] for a in fresh["accounts"] if a["name"] == "Savings")

    created = create_transfer(
        TransferCreate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            from_account_id=_acct(personal_book),
            to_book_id=personal_book["id"],
            to_workspace="personal",
            to_account_id=savings_id,
            amount_cents=5_000,
            date="2026-08-15",
        ),
        owner,
    )
    pair_id = created["from"]["transfer_pair_id"]

    updated = update_transfer(
        pair_id,
        TransferUpdate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            to_book_id=personal_book["id"],
            to_workspace="personal",
            amount_cents=9_000,
            notes="same-book correction",
        ),
        owner,
    )
    assert updated["from"]["amount_cents"] == -9_000
    assert updated["to"]["amount_cents"] == 9_000
    assert updated["from"]["notes"] == "same-book correction"
    assert updated["to"]["notes"] == "same-book correction"
    # Re-read from storage too — not just the returned dicts — to rule out a
    # regression where one leg's on-disk copy never actually got written.
    from_stored = fin.get_transaction(
        "Owner", "personal", personal_book["id"], created["from"]["id"]
    )
    to_stored = fin.get_transaction("Owner", "personal", personal_book["id"], created["to"]["id"])
    assert from_stored["amount_cents"] == -9_000
    assert to_stored["amount_cents"] == 9_000


def test_rejects_transfer_to_the_same_account(owner, personal_book):
    with pytest.raises(HTTPException) as exc:
        create_transfer(
            TransferCreate(
                from_book_id=personal_book["id"],
                from_workspace="personal",
                from_account_id=_acct(personal_book),
                to_book_id=personal_book["id"],
                to_workspace="personal",
                to_account_id=_acct(personal_book),
                amount_cents=100,
                date="2026-08-14",
            ),
            owner,
        )
    assert exc.value.status_code == 400


def test_rejects_mismatched_currency(owner, personal_book):
    eur_book = fin.create_book(
        "Owner", "personal", name="Euro trip", created_by="Owner", currency="EUR"
    )
    fin.add_account("Owner", "personal", eur_book["id"], {"name": "Cash", "type": "cash"})
    fresh = fin.get_book("Owner", "personal", eur_book["id"])

    with pytest.raises(HTTPException) as exc:
        create_transfer(
            TransferCreate(
                from_book_id=personal_book["id"],
                from_workspace="personal",
                from_account_id=_acct(personal_book),
                to_book_id=eur_book["id"],
                to_workspace="personal",
                to_account_id=fresh["accounts"][0]["id"],
                amount_cents=100,
                date="2026-08-14",
            ),
            owner,
        )
    assert exc.value.status_code == 400
    assert "currency" in exc.value.detail.lower()


def test_rejects_workspace_the_user_isnt_entitled_to(owner, personal_only, business_book):
    # personal_only genuinely owns this book (so the *from* side resolves
    # cleanly) but isn't entitled to "business" at all — the interesting
    # rejection is specifically the *to* side's workspace check.
    own_book = fin.create_book("Member", "personal", name="Member's Own", created_by="Member")
    fin.add_account("Member", "personal", own_book["id"], {"name": "Wallet", "type": "cash"})
    fresh = fin.get_book("Member", "personal", own_book["id"])

    with pytest.raises(HTTPException) as exc:
        create_transfer(
            TransferCreate(
                from_book_id=own_book["id"],
                from_workspace="personal",
                from_account_id=fresh["accounts"][0]["id"],
                to_book_id=business_book["id"],
                to_workspace="business",
                to_account_id=_acct(business_book),
                amount_cents=100,
                date="2026-08-14",
            ),
            personal_only,
        )
    assert exc.value.status_code == 403


def test_rejects_contribute_only_access_on_either_book(brain, owner, personal_book):
    worker = auth_service.create_user("worker@example.com", "password123", "Worker", role="member")
    fin.update_access(
        "Owner",
        "personal",
        personal_book["id"],
        shared_with=[{"target": "Worker", "access": "contribute"}],
    )
    fin.respond_share("Worker", "Owner", "personal", personal_book["id"], accept=True)

    savings = fin.create_book("Owner", "personal", name="Savings", created_by="Owner")
    fin.add_account("Owner", "personal", savings["id"], {"name": "Vault", "type": "savings"})
    fresh_savings = fin.get_book("Owner", "personal", savings["id"])
    fin.update_access(
        "Owner", "personal", savings["id"], shared_with=[{"target": "Worker", "access": "edit"}]
    )
    fin.respond_share("Worker", "Owner", "personal", savings["id"], accept=True)

    with pytest.raises(HTTPException) as exc:
        create_transfer(
            TransferCreate(
                from_book_id=personal_book["id"],  # only contribute access here
                from_workspace="personal",
                from_account_id=_acct(personal_book),
                to_book_id=savings["id"],
                to_workspace="personal",
                to_account_id=fresh_savings["accounts"][0]["id"],
                amount_cents=100,
                date="2026-08-14",
            ),
            worker,
        )
    assert exc.value.status_code == 403


def test_reports_exclude_transfer_legs_from_gross_sums_and_categories(
    owner, personal_book, business_book
):
    fin.add_transaction(
        "Owner",
        "personal",
        personal_book,
        {
            "date": "2026-08-14",
            "amount_cents": 20_000,
            "account_id": _acct(personal_book),
            "category": "Salary",
        },
        created_by="Owner",
    )
    create_transfer(
        TransferCreate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            from_account_id=_acct(personal_book),
            to_book_id=business_book["id"],
            to_workspace="business",
            to_account_id=_acct(business_book),
            amount_cents=10_000,
            date="2026-08-14",
        ),
        owner,
    )
    fresh = fin.get_book("Owner", "personal", personal_book["id"])
    report = reports.monthly_report("Owner", "personal", fresh, "2026-08")
    assert report["income_cents"] == 20_000  # the transfer leg's -10_000 never counted as expense
    assert report["expense_cents"] == 0
    assert "" not in [
        c["category"] for c in report["categories"]
    ]  # no phantom uncategorized bucket

    pnl = reports.pnl("Owner", "personal", fresh, 2026, period="month", month=8)
    assert pnl["expense_cents"] == 0


def test_budget_status_excludes_transfer_legs(owner, personal_book):
    planning.set_budgets(
        "Owner",
        "personal",
        personal_book,
        [{"category": "Groceries", "monthly_limit_cents": 5_000}],
    )
    fin.add_transaction(
        "Owner",
        "personal",
        personal_book,
        {
            "date": "2026-08-14",
            "amount_cents": -1_000,
            "account_id": _acct(personal_book),
            "category": "Groceries",
        },
        created_by="Owner",
    )
    savings = fin.create_book("Owner", "personal", name="Savings", created_by="Owner")
    fin.add_account("Owner", "personal", savings["id"], {"name": "Vault", "type": "savings"})
    fresh_savings = fin.get_book("Owner", "personal", savings["id"])
    create_transfer(
        TransferCreate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            from_account_id=_acct(personal_book),
            to_book_id=savings["id"],
            to_workspace="personal",
            to_account_id=fresh_savings["accounts"][0]["id"],
            amount_cents=4_500,
            date="2026-08-14",
        ),
        owner,
    )
    fresh = fin.get_book("Owner", "personal", personal_book["id"])
    status = planning.budget_status("Owner", "personal", fresh, "2026-08")
    groceries = next(b for b in status if b["category"] == "Groceries")
    assert groceries["spent_cents"] == 1_000  # not 5_500 — the transfer leg didn't count


def test_transfer_leg_never_false_matches_a_recurring_bill(owner, personal_book):
    """The whole reason on_transactions_added() is deliberately skipped for
    transfer legs: match_bill() is category-blind (account+sign+amount
    tolerance+date tolerance only)."""
    # Relative to today, not a hardcoded date — this only needs to land
    # inside upcoming_recurring()'s 30-day/3-day-grace window, not on any
    # specific calendar date (a fixed past date ages out of both).
    due = (date.today() + timedelta(days=5)).isoformat()
    planning.add_recurring(
        "Owner",
        "personal",
        personal_book,
        {
            "name": "Rent",
            "amount_cents": -10_000,
            "account_id": _acct(personal_book),
            "cadence": "monthly",
            "next_due": due,
        },
        created_by="Owner",
    )
    savings = fin.create_book("Owner", "personal", name="Savings", created_by="Owner")
    fin.add_account("Owner", "personal", savings["id"], {"name": "Vault", "type": "savings"})
    fresh_savings = fin.get_book("Owner", "personal", savings["id"])
    create_transfer(
        TransferCreate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            from_account_id=_acct(personal_book),
            to_book_id=savings["id"],
            to_workspace="personal",
            to_account_id=fresh_savings["accounts"][0]["id"],
            amount_cents=10_000,
            date=due,
        ),
        owner,
    )
    upcoming = planning.upcoming_recurring("Owner", "personal", personal_book["id"], days=30)
    rent = next(r for r in upcoming["upcoming"] if r["name"] == "Rent")
    assert rent["next_due"] == due  # not advanced — the transfer leg never fed the bill matcher


def test_update_transfer_moves_both_legs_together(owner, personal_book, business_book):
    created = create_transfer(
        TransferCreate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            from_account_id=_acct(personal_book),
            to_book_id=business_book["id"],
            to_workspace="business",
            to_account_id=_acct(business_book),
            amount_cents=10_000,
            date="2026-08-14",
        ),
        owner,
    )
    pair_id = created["from"]["transfer_pair_id"]

    updated = update_transfer(
        pair_id,
        TransferUpdate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            to_book_id=business_book["id"],
            to_workspace="business",
            amount_cents=15_000,
            notes="corrected amount",
        ),
        owner,
    )
    assert updated["from"]["amount_cents"] == -15_000
    assert updated["to"]["amount_cents"] == 15_000
    assert updated["from"]["notes"] == "corrected amount"
    assert updated["to"]["notes"] == "corrected amount"


def test_delete_transfer_removes_both_legs(owner, personal_book, business_book):
    created = create_transfer(
        TransferCreate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            from_account_id=_acct(personal_book),
            to_book_id=business_book["id"],
            to_workspace="business",
            to_account_id=_acct(business_book),
            amount_cents=10_000,
            date="2026-08-14",
        ),
        owner,
    )
    pair_id = created["from"]["transfer_pair_id"]

    delete_transfer(
        pair_id,
        from_book_id=personal_book["id"],
        from_workspace="personal",
        to_book_id=business_book["id"],
        to_workspace="business",
        current_user=owner,
    )
    assert (
        fin.get_transaction("Owner", "personal", personal_book["id"], created["from"]["id"]) is None
    )
    assert (
        fin.get_transaction("Owner", "business", business_book["id"], created["to"]["id"]) is None
    )


def test_single_transaction_endpoints_reject_editing_a_transfer_leg_directly(
    owner, personal_book, business_book
):
    created = create_transfer(
        TransferCreate(
            from_book_id=personal_book["id"],
            from_workspace="personal",
            from_account_id=_acct(personal_book),
            to_book_id=business_book["id"],
            to_workspace="business",
            to_account_id=_acct(business_book),
            amount_cents=10_000,
            date="2026-08-14",
        ),
        owner,
    )

    with pytest.raises(HTTPException) as exc:
        single_tx_update(
            personal_book["id"],
            created["from"]["id"],
            TransactionUpdate(notes="sneaky direct edit"),
            owner,
            "personal",
        )
    assert exc.value.status_code == 409

    with pytest.raises(HTTPException) as exc:
        single_tx_delete(personal_book["id"], created["from"]["id"], owner, "personal")
    assert exc.value.status_code == 409
