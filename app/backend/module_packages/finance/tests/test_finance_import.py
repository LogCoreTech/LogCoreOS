"""CSV import — moved from tests/test_simplefin_service.py when finance/
converted (2026-08-28), since finance_import_service.py moved into this
module package (as import_service.py). Split from the SimpleFIN-specific
tests, which stayed in tests/test_simplefin_service.py alongside
simplefin_service.py (core — scheduler.py's job_simplefin_sync imports it
directly, the same "real external consumer" bar that keeps
n8n_service.py/finance_planning_service.py core)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.finance.backend import import_service as csv_svc
from services import finance_service as fin


@pytest.fixture()
def book(brain):
    return fin.create_book("Alice", "personal", name="Family budget", created_by="Alice")


@pytest.fixture()
def checking(brain, book):
    return fin.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking"}
    )


CSV_CONTENT = b"""Date,Description,Amount
2026-07-01,KROGER #123,-45.99
2026-07-02,ACME PAYROLL,"2,500.00"
2026-07-03,COFFEE SHOP,(4.50)
"""


def test_csv_preview():
    preview = csv_svc.preview_csv(CSV_CONTENT)
    assert preview["headers"] == ["Date", "Description", "Amount"]
    assert preview["total_rows"] == 3
    assert len(preview["rows"]) == 3


def test_csv_amount_and_date_parsing():
    assert csv_svc.parse_amount("-45.99") == -4599
    assert csv_svc.parse_amount("(4.50)") == -450
    assert csv_svc.parse_amount("$2,500.00") == 250000
    assert csv_svc.parse_date("07/03/2026") == "2026-07-03"
    assert csv_svc.parse_date("2026-07-03") == "2026-07-03"
    with pytest.raises(ValueError):
        csv_svc.parse_date("yesterday")


def test_csv_commit_and_reimport_skips(brain, book, checking):
    fresh = fin.get_book("Alice", "personal", book["id"])
    mapping = {
        "account_id": checking["id"],
        "date_col": "Date",
        "amount_col": "Amount",
        "payee_col": "Description",
    }
    result = csv_svc.commit_csv("Alice", "personal", fresh, CSV_CONTENT, mapping, "Alice")
    assert result["created"] == 3
    items, total = fin.list_transactions("Alice", "personal", book["id"])
    assert total == 3
    assert {t["source"] for t in items} == {"csv"}
    paren = next(t for t in items if t["payee"] == "COFFEE SHOP")
    assert paren["amount_cents"] == -450

    # Re-import the exact same file → everything skipped by import_hash
    result = csv_svc.commit_csv("Alice", "personal", fresh, CSV_CONTENT, mapping, "Alice")
    assert result["created"] == 0
    assert result["skipped"] == 3


def test_csv_invert_amounts(brain, book, checking):
    fresh = fin.get_book("Alice", "personal", book["id"])
    content = b"Date,Amount\n2026-07-05,45.99\n"
    mapping = {
        "account_id": checking["id"],
        "date_col": "Date",
        "amount_col": "Amount",
        "invert_amounts": True,
    }
    csv_svc.commit_csv("Alice", "personal", fresh, content, mapping, "Alice")
    items, _ = fin.list_transactions("Alice", "personal", book["id"])
    assert items[0]["amount_cents"] == -4599


def test_csv_bad_rows_reported_not_fatal(brain, book, checking):
    fresh = fin.get_book("Alice", "personal", book["id"])
    content = b"Date,Amount\n2026-07-05,45.99\nnot-a-date,1.00\n2026-07-06,oops\n"
    mapping = {"account_id": checking["id"], "date_col": "Date", "amount_col": "Amount"}
    result = csv_svc.commit_csv("Alice", "personal", fresh, content, mapping, "Alice")
    assert result["created"] == 1
    assert len(result["errors"]) == 2
