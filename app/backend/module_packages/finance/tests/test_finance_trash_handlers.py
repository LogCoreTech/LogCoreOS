"""Tests for finance/backend/trash_handlers.py — the per-module side of the
trash registry contract (see services/trash_service.py's module docstring
and module_registry.py's trash_dispatch()/owned_trash_types). Finance owns
the most record types of any module (10, across 3 core services) — this
file exercises describe()/restore() for each one directly, plus the full
delete-then-restore round trip through the real service functions for the
highest-risk cases (book's whole-directory move, transaction+receipts,
a standalone receipt file)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.finance.backend import trash_handlers
from module_packages.finance.manifest import MODULE
from services import auth_service
from services import finance_invoice_service as invoicing
from services import finance_planning_service as planning
from services import finance_service, mod_store_service, trash_service

USER = "TestUser"


@pytest.fixture()
def user_brain(brain):
    mod_store_service.mark_installed("finance", by="test-fixture")
    user_dir = brain / "USERS" / USER / "Finance"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def _book(**kwargs):
    return finance_service.create_book(
        USER, "personal", kwargs.pop("name", "Household"), USER, **kwargs
    )


def _trash_entries():
    return trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")


def test_record_types_match_manifest():
    assert trash_handlers.RECORD_TYPES == MODULE.owned_trash_types


def test_describe_covers_every_record_type():
    assert trash_handlers.describe("book", {"name": "Household"})[0] == "Household"
    assert trash_handlers.describe("account", {"name": "Checking"})[0] == "Checking"
    title, subtitle = trash_handlers.describe(
        "transaction", {"payee": "Costco", "amount_cents": -5000}
    )
    assert title == "Costco"
    assert "$50.00" in subtitle
    assert trash_handlers.describe("receipt", {"filename": "receipt.pdf"})[0] == "receipt.pdf"
    title, subtitle = trash_handlers.describe(
        "rule", {"payee_norm": "costco", "category": "Groceries"}
    )
    assert "Groceries" in subtitle
    assert (
        trash_handlers.describe("recurring", {"name": "Netflix", "amount_cents": -1500})[0]
        == "Netflix"
    )
    assert (
        trash_handlers.describe("planned", {"name": "Car repair", "amount_cents": -20000})[0]
        == "Car repair"
    )
    assert trash_handlers.describe("client", {"name": "Acme Corp"})[0] == "Acme Corp"
    assert trash_handlers.describe("invoice", {"number": "INV-2026-0001"})[0] == "INV-2026-0001"
    title, _ = trash_handlers.describe("payment", {"amount_cents": 10000})
    assert "$100.00" in title


def test_delete_book_moves_whole_directory_and_restore_brings_it_back(user_brain):
    book = _book()
    account = finance_service.add_account(USER, "personal", book["id"], {"name": "Checking"})
    finance_service.add_transaction(
        USER,
        "personal",
        book,
        {"date": "2026-01-01", "amount_cents": -100, "account_id": account["id"]},
        created_by=USER,
    )

    finance_service.delete_book(USER, "personal", book["id"], deleted_by=USER)
    assert finance_service.get_book(USER, "personal", book["id"]) is None

    entry = next(e for e in _trash_entries() if e["original_id"] == book["id"])
    assert entry["file_ref"] is not None

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["id"] == book["id"]
    assert finance_service.get_book(USER, "personal", book["id"]) is not None
    # The transaction shard came back with the directory, not just the book record.
    txs, total = finance_service.list_transactions(USER, "personal", book["id"])
    assert total == 1


def test_delete_account_and_restore(user_brain):
    book = _book()
    account = finance_service.add_account(USER, "personal", book["id"], {"name": "Savings"})

    finance_service.delete_account(USER, "personal", book["id"], account["id"], deleted_by=USER)
    entry = next(e for e in _trash_entries() if e["original_id"] == account["id"])

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["id"] == account["id"]
    updated_book = finance_service.get_book(USER, "personal", book["id"])
    assert any(a["id"] == account["id"] for a in updated_book["accounts"])


def test_delete_transaction_with_receipt_and_restore(user_brain):
    book = _book()
    account = finance_service.add_account(USER, "personal", book["id"], {"name": "Checking"})
    tx = finance_service.add_transaction(
        USER,
        "personal",
        book,
        {"date": "2026-03-15", "amount_cents": -2500, "account_id": account["id"]},
        created_by=USER,
    )
    finance_service.add_receipt(
        USER, "personal", book["id"], tx["id"], "r.jpg", "image/jpeg", b"fakejpeg"
    )

    finance_service.delete_transaction(USER, "personal", book["id"], tx["id"], deleted_by=USER)
    assert finance_service.get_transaction(USER, "personal", book["id"], tx["id"]) is None

    entry = next(e for e in _trash_entries() if e["original_id"] == tx["id"])
    assert entry["file_ref"] is not None  # the receipts dir moved with it

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["id"] == tx["id"]
    got = finance_service.get_transaction(USER, "personal", book["id"], tx["id"])
    assert got is not None
    assert len(got["attachments"]) == 1


def test_delete_receipt_standalone_and_restore(user_brain):
    book = _book()
    account = finance_service.add_account(USER, "personal", book["id"], {"name": "Checking"})
    tx = finance_service.add_transaction(
        USER,
        "personal",
        book,
        {"date": "2026-03-15", "amount_cents": -2500, "account_id": account["id"]},
        created_by=USER,
    )
    meta = finance_service.add_receipt(
        USER, "personal", book["id"], tx["id"], "r.jpg", "image/jpeg", b"fakejpeg"
    )

    finance_service.delete_receipt(
        USER, "personal", book["id"], tx["id"], meta["id"], deleted_by=USER
    )
    got = finance_service.get_transaction(USER, "personal", book["id"], tx["id"])
    assert got["attachments"] == []

    entry = next(e for e in _trash_entries() if e["original_id"] == meta["id"])
    trash_handlers.restore(USER, "personal", entry)

    got = finance_service.get_transaction(USER, "personal", book["id"], tx["id"])
    assert len(got["attachments"]) == 1
    assert got["attachments"][0]["id"] == meta["id"]


def test_delete_rule_and_restore(user_brain):
    book = _book()
    finance_service.learn_rule(USER, "personal", book["id"], "Costco", "Groceries")
    rule = finance_service.list_rules(USER, "personal", book["id"])[0]

    finance_service.delete_rule(USER, "personal", book["id"], rule["id"], deleted_by=USER)
    assert finance_service.list_rules(USER, "personal", book["id"]) == []

    entry = next(e for e in _trash_entries() if e["original_id"] == rule["id"])
    trash_handlers.restore(USER, "personal", entry)
    assert len(finance_service.list_rules(USER, "personal", book["id"])) == 1


def test_delete_recurring_and_restore(user_brain):
    book = _book()
    account = finance_service.add_account(USER, "personal", book["id"], {"name": "Checking"})
    item = planning.add_recurring(
        USER,
        "personal",
        book,
        {
            "name": "Netflix",
            "amount_cents": -1500,
            "account_id": account["id"],
            "cadence": "monthly",
            "next_due": "2026-04-01",
        },
        created_by=USER,
    )

    planning.delete_recurring(USER, "personal", book["id"], item["id"], deleted_by=USER)
    assert planning.list_recurring(USER, "personal", book["id"]) == []

    entry = next(e for e in _trash_entries() if e["original_id"] == item["id"])
    trash_handlers.restore(USER, "personal", entry)
    assert len(planning.list_recurring(USER, "personal", book["id"])) == 1


def test_delete_planned_and_restore(user_brain):
    book = _book()
    account = finance_service.add_account(USER, "personal", book["id"], {"name": "Checking"})
    item = planning.add_planned(
        USER,
        "personal",
        book,
        {
            "name": "Car repair",
            "amount_cents": -20000,
            "account_id": account["id"],
            "date": "2026-05-01",
        },
        created_by=USER,
    )

    planning.delete_planned(USER, "personal", book["id"], item["id"], deleted_by=USER)
    assert planning.list_planned(USER, "personal", book["id"]) == []

    entry = next(e for e in _trash_entries() if e["original_id"] == item["id"])
    trash_handlers.restore(USER, "personal", entry)
    assert len(planning.list_planned(USER, "personal", book["id"])) == 1


def test_delete_client_and_restore(user_brain):
    book = _book()
    client = invoicing.add_client(USER, "personal", book["id"], {"name": "Acme"}, created_by=USER)

    invoicing.delete_client(USER, "personal", book["id"], client["id"], deleted_by=USER)
    assert invoicing.list_clients(USER, "personal", book["id"]) == []

    entry = next(e for e in _trash_entries() if e["original_id"] == client["id"])
    trash_handlers.restore(USER, "personal", entry)
    assert len(invoicing.list_clients(USER, "personal", book["id"])) == 1


def test_delete_invoice_and_restore(user_brain):
    book = _book()
    invoice = invoicing.create_invoice(
        USER,
        "personal",
        book["id"],
        {
            "due_date": "2026-06-01",
            "line_items": [{"description": "Consulting", "unit_cents": 10000}],
        },
        created_by=USER,
    )

    invoicing.delete_invoice(USER, "personal", book["id"], invoice["id"], deleted_by=USER)
    assert invoicing.list_invoices(USER, "personal", book["id"]) == []

    entry = next(e for e in _trash_entries() if e["original_id"] == invoice["id"])
    trash_handlers.restore(USER, "personal", entry)
    assert len(invoicing.list_invoices(USER, "personal", book["id"])) == 1


def test_delete_payment_and_restore(user_brain):
    book = _book()
    account = finance_service.add_account(USER, "personal", book["id"], {"name": "Checking"})
    invoice = invoicing.create_invoice(
        USER,
        "personal",
        book["id"],
        {
            "due_date": "2026-06-01",
            "line_items": [{"description": "Consulting", "unit_cents": 10000}],
        },
        created_by=USER,
    )
    invoicing.record_payment(
        USER,
        "personal",
        book["id"],
        invoice["id"],
        {"amount_cents": 5000, "date": "2026-06-05"},
        created_by=USER,
    )
    updated_invoice = invoicing.get_invoice(USER, "personal", book["id"], invoice["id"])
    payment = updated_invoice["payments"][0]

    invoicing.delete_payment(
        USER, "personal", book["id"], invoice["id"], payment["id"], deleted_by=USER
    )
    assert invoicing.get_invoice(USER, "personal", book["id"], invoice["id"])["payments"] == []

    entry = next(e for e in _trash_entries() if e["original_id"] == payment["id"])
    trash_handlers.restore(USER, "personal", entry)
    got = invoicing.get_invoice(USER, "personal", book["id"], invoice["id"])
    assert len(got["payments"]) == 1


def test_restore_conflict_raises_when_id_already_present(user_brain):
    book = _book()
    entry = {"payload": dict(book), "record_type": "book", "file_ref": None}

    with pytest.raises(ValueError):
        trash_handlers.restore(USER, "personal", entry)


def test_access_check_always_true():
    assert trash_handlers.access_check({"name": USER}, "personal", {}) is True
