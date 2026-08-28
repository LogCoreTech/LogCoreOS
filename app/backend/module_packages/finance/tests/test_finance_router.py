"""Router-level tests for module_packages/finance/backend/router.py — the
first-ever HTTP-layer coverage of this specific file (finance_service.py's
own CRUD/access-resolution logic is already covered extensively by
tests/test_finance_service.py/test_finance_sharing.py; router_transfers.py
and router_banking.py already had their own direct-call tests before this
conversion — see test_finance_transfers.py/test_simplefin_pool.py, both
moved into this same directory). This file is about router.py's own body
logic: pool-book creation admin-gating, contribute-vs-edit enforcement,
delete-blocked-while-has-transactions, and balance-stripping for
contribute viewers without see_balances.

Endpoint functions are called directly with a pre-resolved user dict and a
plain workspace string, matching this test suite's established convention
(see test_assets_router.py/test_contacts_router.py) — Depends(_require_finance)/
Depends(get_workspace) are bypassed the same way Depends(require_admin) is
elsewhere; this file tests the endpoints' own body logic, not the
require_module dependency chain itself (untested anywhere in this suite
today, a pre-existing, systemic gap this conversion isn't scoped to
close)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.finance.backend.router import (
    AccountCreate,
    BookCreate,
    BookUpdate,
    TransactionCreate,
    add_account,
    add_transaction,
    create_book,
    delete_account,
    delete_book,
    get_book,
    list_books,
    update_book,
)


@pytest.fixture()
def users(brain):
    from services import auth_service

    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_create_and_list_books(users):
    create_book(BookCreate(name="Household", pool=False), users["alice"], "personal")

    result = list_books(False, users["alice"], "personal")

    assert any(b["name"] == "Household" for b in result)


def test_create_pool_book_requires_admin(users):
    with pytest.raises(HTTPException) as exc:
        create_book(BookCreate(name="Team Fund", pool=True), users["bob"], "personal")
    assert exc.value.status_code == 403


def test_create_pool_book_allowed_for_admin(users):
    created = create_book(BookCreate(name="Family Fund", pool=True), users["alice"], "personal")

    assert created["_owner"] == "household"


def test_get_book_404_when_missing(users):
    with pytest.raises(HTTPException) as exc:
        get_book("11111111-1111-1111-1111-111111111111", users["alice"], "personal")
    assert exc.value.status_code == 404


def test_update_book_renames(users):
    created = create_book(BookCreate(name="Old Name", pool=False), users["alice"], "personal")

    result = update_book(created["id"], BookUpdate(name="New Name"), users["alice"], "personal")

    assert result["name"] == "New Name"


def test_add_account_and_transaction(users):
    book = create_book(BookCreate(name="Checking Book", pool=False), users["alice"], "personal")
    account = add_account(
        book["id"], AccountCreate(name="Checking", type="checking"), users["alice"], "personal"
    )

    tx = add_transaction(
        book["id"],
        TransactionCreate(date="2026-08-28", amount_cents=-1500, account_id=account["id"]),
        users["alice"],
        "personal",
    )

    assert tx["amount_cents"] == -1500


def test_delete_account_blocked_while_has_transactions(users):
    book = create_book(BookCreate(name="Blocked Book", pool=False), users["alice"], "personal")
    account = add_account(
        book["id"], AccountCreate(name="Checking", type="checking"), users["alice"], "personal"
    )
    add_transaction(
        book["id"],
        TransactionCreate(date="2026-08-28", amount_cents=500, account_id=account["id"]),
        users["alice"],
        "personal",
    )

    with pytest.raises(HTTPException) as exc:
        delete_account(book["id"], account["id"], users["alice"], "personal")
    assert exc.value.status_code == 409


def test_delete_book_blocked_while_has_transactions(users):
    book = create_book(BookCreate(name="Also Blocked", pool=False), users["alice"], "personal")
    account = add_account(
        book["id"], AccountCreate(name="Checking", type="checking"), users["alice"], "personal"
    )
    add_transaction(
        book["id"],
        TransactionCreate(date="2026-08-28", amount_cents=500, account_id=account["id"]),
        users["alice"],
        "personal",
    )

    with pytest.raises(HTTPException) as exc:
        delete_book(book["id"], users["alice"], "personal")
    assert exc.value.status_code == 409


def test_delete_empty_book(users):
    book = create_book(BookCreate(name="Empty Book", pool=False), users["alice"], "personal")

    delete_book(book["id"], users["alice"], "personal")

    result = list_books(False, users["alice"], "personal")
    assert not any(b["id"] == book["id"] for b in result)


def test_delete_pool_book_blocked_for_non_admin(users):
    book = create_book(BookCreate(name="Pool Book", pool=True), users["alice"], "personal")

    with pytest.raises(HTTPException) as exc:
        delete_book(book["id"], users["bob"], "personal")
    assert exc.value.status_code == 403


def test_contribute_without_see_balances_strips_balances(users):
    book = create_book(BookCreate(name="Contribute Book", pool=False), users["alice"], "personal")
    from services import finance_service

    finance_service.update_access(
        "Alice",
        "personal",
        book["id"],
        shared_with=[
            {
                "target": "Bob",
                "access": "contribute",
                "caps": {"add": ["expense"], "see_balances": False},
            }
        ],
    )
    finance_service.respond_share("Bob", "Alice", "personal", book["id"], True)

    result = get_book(book["id"], users["bob"], "personal")

    assert "balances" not in result
