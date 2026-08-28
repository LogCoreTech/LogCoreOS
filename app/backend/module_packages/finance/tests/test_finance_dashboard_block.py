"""Tests for the Finance Activity / Finance Book Report blocks — moved into
module_packages/finance/backend/dashboard_block.py (from the old, core
services/dashboard_blocks/_finance.py) when finance/ converted (2026-08-28),
gaining module="finance" gating for the first time. No pre-existing test
coverage of either resolver existed before this conversion, so this file
is new, not moved."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from services import auth_service, finance_service
from services.dashboard_blocks.registry import BlockRenderCtx, _load_all_resolvers

_load_all_resolvers()

from module_packages.finance.backend.dashboard_block import (
    resolve_finance_activity,
    resolve_finance_book_report,
)


@pytest.fixture()
def users(brain):
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def _ctx(viewer="Alice", config=None, workspace="personal", is_admin=False, owner="Alice"):
    return BlockRenderCtx(
        viewer=viewer,
        viewer_role="member",
        is_admin=is_admin,
        workspace=workspace,
        config=config or {},
        dashboard_owner=owner,
    )


def test_finance_activity_by_book_returns_recent_transactions(users):
    book = finance_service.create_book("Alice", "personal", name="Ledger", created_by="Alice")
    account = finance_service.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking"}
    )
    finance_service.add_transaction(
        "Alice",
        "personal",
        book,
        {"date": "2026-08-28", "amount_cents": -500, "account_id": account["id"]},
        created_by="Alice",
    )

    result = resolve_finance_activity(_ctx(config={"book_id": book["id"]}))

    assert result.ok is True
    assert len(result.data["transactions"]) == 1


def test_finance_activity_no_access_when_book_not_visible(users):
    book = finance_service.create_book("Alice", "personal", name="Private", created_by="Alice")

    result = resolve_finance_activity(_ctx(viewer="Bob", config={"book_id": book["id"]}))

    assert result.ok is False
    assert result.locked_reason == "no_access"


def test_finance_activity_not_found_with_no_config(users):
    result = resolve_finance_activity(_ctx())
    assert result.ok is False
    assert result.locked_reason == "not_found"


def test_finance_book_report_returns_monthly_totals(users):
    book = finance_service.create_book("Alice", "personal", name="ReportLedger", created_by="Alice")
    account = finance_service.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking"}
    )
    finance_service.add_transaction(
        "Alice",
        "personal",
        book,
        {"date": "2026-08-01", "amount_cents": 1000, "account_id": account["id"]},
        created_by="Alice",
    )

    result = resolve_finance_book_report(_ctx(config={"book_id": book["id"], "month": "2026-08"}))

    assert result.ok is True
    assert result.data["report"]["income_cents"] == 1000
