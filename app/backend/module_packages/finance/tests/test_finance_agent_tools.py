"""Tests for the 9 finance tools that moved into
module_packages/finance/backend/agent_tools.py when finance/ converted
(2026-08-28) — resolved via agent_service._execute_tool's module-dispatch
fallback (still core; routes here via this package's own execute()). No
pre-existing test coverage of these tools' actual execution logic existed
before this conversion (only their schemas, unfiltered by disabled_modules,
which is the enforcement gap this conversion closed — see
tests/test_finance_module_conversion.py for the gating tests themselves),
so this file is new, not moved."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from services import agent_service, auth_service, finance_service, mod_store_service


@pytest.fixture()
def users(brain):
    mod_store_service.mark_installed("finance", by="tester")
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_list_finance_books_tool_includes_balances(users):
    finance_service.create_book("Alice", "personal", name="Main", created_by="Alice")

    result = agent_service._execute_tool(
        "list_finance_books", {}, users["alice"], workspace="personal"
    )

    assert any(b["name"] == "Main" for b in result)
    assert "balances" in result[0]


def test_list_finance_transactions_tool_returns_error_for_missing_book(users):
    result = agent_service._execute_tool(
        "list_finance_transactions",
        {"book_id": "does-not-exist"},
        users["alice"],
        workspace="personal",
    )
    assert "error" in result


def test_add_finance_transaction_tool_logs_expense(users):
    book = finance_service.create_book("Alice", "personal", name="Ledger", created_by="Alice")
    account = finance_service.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking"}
    )

    result = agent_service._execute_tool(
        "add_finance_transaction",
        {"book_id": book["id"], "account_id": account["id"], "amount_cents": -2500},
        users["alice"],
        workspace="personal",
    )

    assert result["amount_cents"] == -2500


def test_add_finance_transaction_tool_blocks_read_only_access(users):
    book = finance_service.create_book("Alice", "personal", name="Private", created_by="Alice")
    account = finance_service.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking"}
    )
    finance_service.update_access(
        "Alice",
        "personal",
        book["id"],
        shared_with=[{"target": "Bob", "access": "read"}],
    )
    finance_service.respond_share("Bob", "Alice", "personal", book["id"], True)

    result = agent_service._execute_tool(
        "add_finance_transaction",
        {"book_id": book["id"], "account_id": account["id"], "amount_cents": -1000},
        users["bob"],
        workspace="personal",
    )
    assert "error" in result


def test_add_finance_transaction_tool_contribute_expense_only_cap(users):
    book = finance_service.create_book("Alice", "personal", name="Capped", created_by="Alice")
    account = finance_service.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking"}
    )
    finance_service.update_access(
        "Alice",
        "personal",
        book["id"],
        shared_with=[
            {"target": "Bob", "access": "contribute", "caps": {"add": ["expense"]}}
        ],
    )
    finance_service.respond_share("Bob", "Alice", "personal", book["id"], True)

    # Allowed: an expense.
    result = agent_service._execute_tool(
        "add_finance_transaction",
        {"book_id": book["id"], "account_id": account["id"], "amount_cents": -500},
        users["bob"],
        workspace="personal",
    )
    assert result["amount_cents"] == -500

    # Blocked: income isn't in the cap.
    result = agent_service._execute_tool(
        "add_finance_transaction",
        {"book_id": book["id"], "account_id": account["id"], "amount_cents": 500},
        users["bob"],
        workspace="personal",
    )
    assert "error" in result


def test_categorize_transaction_tool_learns_rule_for_imported_tx(users):
    book = finance_service.create_book("Alice", "personal", name="Ledger2", created_by="Alice")
    account = finance_service.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking"}
    )
    tx = finance_service.add_transaction(
        "Alice",
        "personal",
        book,
        {"date": "2026-08-28", "amount_cents": -999, "account_id": account["id"], "payee": "COFFEE SHOP", "source": "csv"},
        created_by="Alice",
    )

    result = agent_service._execute_tool(
        "categorize_transaction",
        {"book_id": book["id"], "tx_id": tx["id"], "category": "Dining"},
        users["alice"],
        workspace="personal",
    )

    assert result["category"] == "Dining"


def test_get_finance_report_tool_returns_monthly_report(users):
    book = finance_service.create_book("Alice", "personal", name="ReportBook", created_by="Alice")
    account = finance_service.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking"}
    )
    finance_service.add_transaction(
        "Alice",
        "personal",
        book,
        {"date": "2026-08-01", "amount_cents": -100, "account_id": account["id"]},
        created_by="Alice",
    )

    result = agent_service._execute_tool(
        "get_finance_report",
        {"book_id": book["id"], "month": "2026-08"},
        users["alice"],
        workspace="personal",
    )

    assert result["expense_cents"] == -100


def test_get_balance_projection_tool_returns_itemized_breakdown(users):
    book = finance_service.create_book("Alice", "personal", name="ProjBook", created_by="Alice")
    account = finance_service.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking", "opening_balance_cents": 10000}
    )

    result = agent_service._execute_tool(
        "get_balance_projection",
        {"book_id": book["id"], "account_id": account["id"], "date": "2026-12-01"},
        users["alice"],
        workspace="personal",
    )

    assert "projected_cents" in result


def test_get_budget_status_tool_returns_error_for_missing_book(users):
    result = agent_service._execute_tool(
        "get_budget_status",
        {"book_id": "does-not-exist"},
        users["alice"],
        workspace="personal",
    )
    assert "error" in result


def test_create_invoice_tool_requires_edit_access(users):
    book = finance_service.create_book("Alice", "personal", name="InvBook", created_by="Alice")
    finance_service.update_access(
        "Alice",
        "personal",
        book["id"],
        shared_with=[{"target": "Bob", "access": "read"}],
    )
    finance_service.respond_share("Bob", "Alice", "personal", book["id"], True)

    result = agent_service._execute_tool(
        "create_invoice",
        {"book_id": book["id"], "due_date": "2026-09-15", "line_items": [{"description": "Work", "unit_cents": 10000}]},
        users["bob"],
        workspace="personal",
    )
    assert "error" in result


def test_create_invoice_tool_creates_draft_for_owner(users):
    book = finance_service.create_book("Alice", "personal", name="InvBook2", created_by="Alice")

    result = agent_service._execute_tool(
        "create_invoice",
        {"book_id": book["id"], "due_date": "2026-09-15", "line_items": [{"description": "Work", "unit_cents": 10000}]},
        users["alice"],
        workspace="personal",
    )

    assert result["status"] == "draft"


def test_mark_invoice_paid_tool_records_full_payment(users):
    book = finance_service.create_book("Alice", "personal", name="InvBook3", created_by="Alice")
    from services import finance_invoice_service

    invoice = finance_invoice_service.create_invoice(
        "Alice",
        "personal",
        book["id"],
        {"due_date": "2026-09-15", "line_items": [{"description": "Work", "unit_cents": 5000}]},
        created_by="Alice",
    )

    result = agent_service._execute_tool(
        "mark_invoice_paid",
        {"book_id": book["id"], "invoice_id": invoice["id"]},
        users["alice"],
        workspace="personal",
    )

    assert result["status"] == "paid"
