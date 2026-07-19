"""Finance Phase D: clients, invoices, payments, AR, tax reports, receipts."""

from datetime import date, timedelta

import pytest

from services import finance_invoice_service as inv
from services import finance_reports as reports
from services import finance_service as fin


@pytest.fixture()
def book(brain):
    return fin.create_book("Alice", "business", name="LLC books", created_by="Alice")


@pytest.fixture()
def checking(brain, book):
    return fin.add_account(
        "Alice", "business", book["id"], {"name": "Business checking", "type": "checking"}
    )


@pytest.fixture()
def client(brain, book):
    return inv.add_client(
        "Alice", "business", book["id"], {"name": "Acme LLC", "email": "ap@acme.test"}, "Alice"
    )


def _invoice(book, client, due=None, items=None, tax=0):
    return inv.create_invoice(
        "Alice",
        "business",
        book["id"],
        {
            "client_id": client["id"],
            "due_date": due or (date.today() + timedelta(days=30)).isoformat(),
            "line_items": items or [{"description": "Consulting", "qty": 10, "unit_cents": 150_00}],
            "tax_pct": tax,
        },
        "Alice",
    )


# ---------------------------------------------------------------------------
# Invoices: numbering, totals, partial payments, derived overdue
# ---------------------------------------------------------------------------


def test_invoice_numbering_sequence(brain, book, client):
    first = _invoice(book, client)
    second = _invoice(book, client)
    year = date.today().year
    assert first["number"] == f"INV-{year}-0001"
    assert second["number"] == f"INV-{year}-0002"
    # Custom prefix applies to the next invoice
    fin.update_book("Alice", "business", book["id"], {"invoice_prefix": "ACME"})
    third = _invoice(book, client)
    assert third["number"].startswith("ACME-")


def test_invoice_totals_with_tax(brain, book, client):
    invoice = _invoice(
        book,
        client,
        items=[
            {"description": "Consulting", "qty": 10, "unit_cents": 150_00},
            {"description": "Materials", "qty": 1, "unit_cents": 250_00},
        ],
        tax=10,
    )
    assert invoice["subtotal_cents"] == 1500_00 + 250_00
    assert invoice["total_cents"] == round((1500_00 + 250_00) * 1.10)
    assert invoice["paid_cents"] == 0
    assert invoice["balance_cents"] == invoice["total_cents"]
    assert invoice["status"] == "draft"


def test_partial_payment_and_auto_paid(brain, book, client, checking):
    invoice = _invoice(book, client)  # 1500.00 total
    inv.update_invoice("Alice", "business", book["id"], invoice["id"], {"status": "sent"})

    after_partial = inv.record_payment(
        "Alice",
        "business",
        book["id"],
        invoice["id"],
        {"amount_cents": 500_00, "method": "check", "account_id": checking["id"]},
        "Alice",
    )
    assert after_partial["paid_cents"] == 500_00
    assert after_partial["balance_cents"] == 1000_00
    assert after_partial["status"] == "sent"  # not fully paid yet

    # The payment created a LINKED income transaction
    tx_id = after_partial["payments"][0]["tx_id"]
    tx = fin.get_transaction("Alice", "business", book["id"], tx_id)
    assert tx["amount_cents"] == 500_00
    assert tx["invoice_id"] == invoice["id"]
    assert tx["client_id"] == client["id"]
    assert tx["payee"] == "Acme LLC"

    # Paying the rest flips status to paid automatically
    done = inv.record_payment(
        "Alice", "business", book["id"], invoice["id"], {"amount_cents": 1000_00}, "Alice"
    )
    assert done["balance_cents"] == 0
    assert done["status"] == "paid"

    # Removing a payment reopens it
    reopened = inv.delete_payment(
        "Alice", "business", book["id"], invoice["id"], done["payments"][1]["id"]
    )
    assert reopened["status"] == "sent"
    assert reopened["balance_cents"] == 1000_00


def test_overdue_is_derived(brain, book, client):
    past_due = (date.today() - timedelta(days=5)).isoformat()
    invoice = _invoice(book, client, due=past_due)
    # Draft past due → NOT overdue (never sent)
    assert inv.get_invoice("Alice", "business", book["id"], invoice["id"])["overdue"] is False
    inv.update_invoice("Alice", "business", book["id"], invoice["id"], {"status": "sent"})
    assert inv.get_invoice("Alice", "business", book["id"], invoice["id"])["overdue"] is True
    # Paying clears it
    inv.record_payment(
        "Alice", "business", book["id"], invoice["id"], {"amount_cents": 1500_00}, "Alice"
    )
    assert inv.get_invoice("Alice", "business", book["id"], invoice["id"])["overdue"] is False


def test_invoice_validation(brain, book, client):
    with pytest.raises(ValueError):
        inv.create_invoice(
            "Alice",
            "business",
            book["id"],
            {"client_id": client["id"], "due_date": "2026-08-01", "line_items": []},
            "Alice",
        )
    with pytest.raises(ValueError):
        _invoice(book, client, items=[{"description": "", "qty": 1, "unit_cents": 100}])
    with pytest.raises(ValueError):
        inv.create_invoice(
            "Alice",
            "business",
            book["id"],
            {
                "client_id": "not-a-client",
                "due_date": "2026-08-01",
                "line_items": [{"description": "X", "qty": 1, "unit_cents": 100}],
            },
            "Alice",
        )


# ---------------------------------------------------------------------------
# Clients + AR
# ---------------------------------------------------------------------------


def test_client_delete_blocked_with_invoices(brain, book, client):
    _invoice(book, client)
    assert inv.client_has_invoices("Alice", "business", book["id"], client["id"])
    empty = inv.add_client("Alice", "business", book["id"], {"name": "No Deals Yet"}, "Alice")
    assert not inv.client_has_invoices("Alice", "business", book["id"], empty["id"])
    assert inv.delete_client("Alice", "business", book["id"], empty["id"])
    # contact_id is reserved for the future CRM and starts null
    assert client["contact_id"] is None


def test_ar_summary_who_is_behind(brain, book, client):
    slowpay = inv.add_client("Alice", "business", book["id"], {"name": "SlowPay Inc"}, "Alice")
    # Acme: one invoice, fully paid
    paid_inv = _invoice(book, client)
    inv.update_invoice("Alice", "business", book["id"], paid_inv["id"], {"status": "sent"})
    inv.record_payment(
        "Alice", "business", book["id"], paid_inv["id"], {"amount_cents": 1500_00}, "Alice"
    )
    # SlowPay: one overdue invoice, partially paid; one voided (excluded)
    past_due = (date.today() - timedelta(days=10)).isoformat()
    slow_inv = inv.create_invoice(
        "Alice",
        "business",
        book["id"],
        {
            "client_id": slowpay["id"],
            "due_date": past_due,
            "line_items": [{"description": "Job", "qty": 1, "unit_cents": 800_00}],
        },
        "Alice",
    )
    inv.update_invoice("Alice", "business", book["id"], slow_inv["id"], {"status": "sent"})
    inv.record_payment(
        "Alice", "business", book["id"], slow_inv["id"], {"amount_cents": 300_00}, "Alice"
    )
    voided = inv.create_invoice(
        "Alice",
        "business",
        book["id"],
        {
            "client_id": slowpay["id"],
            "due_date": past_due,
            "line_items": [{"description": "Cancelled", "qty": 1, "unit_cents": 999_00}],
        },
        "Alice",
    )
    inv.update_invoice("Alice", "business", book["id"], voided["id"], {"status": "void"})

    summary = inv.ar_summary("Alice", "business", book["id"])
    # Worst offender sorts first
    assert summary[0]["client_name"] == "SlowPay Inc"
    assert summary[0]["outstanding_cents"] == 500_00
    assert summary[0]["overdue_cents"] == 500_00
    assert summary[0]["overdue_count"] == 1
    acme = next(e for e in summary if e["client_name"] == "Acme LLC")
    assert acme["outstanding_cents"] == 0
    assert acme["paid_cents"] == 1500_00
    assert acme["last_payment"] == date.today().isoformat()


# ---------------------------------------------------------------------------
# P&L + tax reports
# ---------------------------------------------------------------------------


def _tx(book, checking, amount, day, category="", **kw):
    return fin.add_transaction(
        "Alice",
        "business",
        book,
        {
            "date": day,
            "amount_cents": amount,
            "account_id": checking["id"],
            "category": category,
            **kw,
        },
        "Alice",
    )


def test_pnl_periods(brain, book, checking):
    fin.update_book(
        "Alice",
        "business",
        book["id"],
        {
            "categories": [
                {"name": "Sales", "kind": "income"},
                {"name": "Supplies", "kind": "expense"},
            ]
        },
    )
    fresh = fin.get_book("Alice", "business", book["id"])
    _tx(fresh, checking, 5000_00, "2026-02-10", "Sales")
    _tx(fresh, checking, -800_00, "2026-02-15", "Supplies")
    _tx(fresh, checking, 3000_00, "2026-07-01", "Sales")

    year_pnl = reports.pnl("Alice", "business", fresh, 2026)
    assert year_pnl["income_cents"] == 8000_00
    assert year_pnl["expense_cents"] == -800_00
    assert year_pnl["net_cents"] == 7200_00

    q1 = reports.pnl("Alice", "business", fresh, 2026, period="quarter", quarter=1)
    assert q1["income_cents"] == 5000_00
    assert q1["net_cents"] == 4200_00

    feb = reports.pnl("Alice", "business", fresh, 2026, period="month", month=2)
    assert feb["transaction_count"] == 2

    with pytest.raises(ValueError):
        reports.pnl("Alice", "business", fresh, 2026, period="quarter")  # missing quarter


def test_tax_summary_and_csv(brain, book, checking):
    fin.update_book("Alice", "business", book["id"], {"tax_categories": ["Supplies", "Travel"]})
    fresh = fin.get_book("Alice", "business", book["id"])
    _tx(fresh, checking, -100_00, "2026-03-01", deductible=True, tax_category="Supplies")
    _tx(
        fresh,
        checking,
        -50_00,
        "2026-04-01",
        deductible=True,
        tax_category="Supplies",
        payee='Bob\'s "Tools"',
    )
    _tx(fresh, checking, -75_00, "2026-05-01", deductible=True)  # unassigned bucket
    _tx(fresh, checking, -999_00, "2026-05-02")  # not deductible

    summary = reports.tax_summary("Alice", "business", fresh, 2026)
    assert summary["total_cents"] == -(100_00 + 50_00 + 75_00)
    assert summary["count"] == 3
    supplies = next(b for b in summary["buckets"] if b["tax_category"] == "Supplies")
    assert supplies["amount_cents"] == -150_00 and supplies["count"] == 2

    csv_text = reports.tax_summary_csv("Alice", "business", fresh, 2026)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "date,payee,category,tax_category,amount"
    assert len(lines) == 4  # header + 3 deductible rows
    assert "-999.00" not in csv_text


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


def test_receipt_lifecycle(brain, book, checking):
    tx = _tx(fin.get_book("Alice", "business", book["id"]), checking, -45_00, "2026-07-01")
    meta = fin.add_receipt(
        "Alice", "business", book["id"], tx["id"], "lunch ../receipt.jpg", "image/jpeg", b"JPEGDATA"
    )
    # Disk name is the uuid, original name sanitized in metadata only
    assert "/" not in meta["filename"] and ".." not in meta["filename"]
    found = fin.get_receipt("Alice", "business", book["id"], tx["id"], meta["id"])
    assert found is not None
    path, mime, _fname = found
    assert path.name == f"{meta['id']}.jpg"
    assert path.read_bytes() == b"JPEGDATA"

    fresh_tx = fin.get_transaction("Alice", "business", book["id"], tx["id"])
    assert len(fresh_tx["attachments"]) == 1

    assert fin.delete_receipt("Alice", "business", book["id"], tx["id"], meta["id"])
    assert fin.get_receipt("Alice", "business", book["id"], tx["id"], meta["id"]) is None
    assert fin.get_transaction("Alice", "business", book["id"], tx["id"])["attachments"] == []


def test_receipt_validation(brain, book, checking):
    tx = _tx(fin.get_book("Alice", "business", book["id"]), checking, -45_00, "2026-07-01")
    with pytest.raises(ValueError):
        fin.add_receipt(
            "Alice", "business", book["id"], tx["id"], "x.exe", "application/x-exe", b"nope"
        )
    with pytest.raises(ValueError):
        fin.add_receipt(
            "Alice",
            "business",
            book["id"],
            tx["id"],
            "big.jpg",
            "image/jpeg",
            b"x" * (fin.MAX_RECEIPT_BYTES + 1),
        )


def test_delete_transaction_removes_receipts(brain, book, checking):
    tx = _tx(fin.get_book("Alice", "business", book["id"]), checking, -45_00, "2026-07-01")
    meta = fin.add_receipt(
        "Alice", "business", book["id"], tx["id"], "r.pdf", "application/pdf", b"PDF"
    )
    receipt_dir = fin._receipts_dir("Alice", "business", book["id"], tx["id"])
    assert receipt_dir.exists()
    fin.delete_transaction("Alice", "business", book["id"], tx["id"])
    assert not receipt_dir.exists()
    assert meta["id"]  # (referenced to satisfy lints)


# ---------------------------------------------------------------------------
# Deal-billed invoices (deal_id) + payment tx stamping + cross-book scan
# ---------------------------------------------------------------------------


def _deal_with_assets(asset_ids):
    from services import contacts_service as crm

    c = crm.create_contact("Alice", "business", {"name": "Acme"}, "Alice")
    d = crm.add_deal("Alice", "business", c["id"], {"title": "Job"}, "Alice")
    for aid in asset_ids:
        crm.link_asset("Alice", "business", d["id"], aid)
    return crm.list_deals("Alice", "business", c["id"])[0]


def _deal_invoice(book, client, deal_id):
    return inv.create_invoice(
        "Alice",
        "business",
        book["id"],
        {
            "client_id": client["id"],
            "deal_id": deal_id,
            "due_date": (date.today() + timedelta(days=10)).isoformat(),
            "line_items": [{"description": "Work", "qty": 1, "unit_cents": 100_00}],
        },
        "Alice",
    )


def test_invoice_deal_id_stored(brain, book, client):
    d = _deal_with_assets([])
    made = _deal_invoice(book, client, d["id"])
    assert made["deal_id"] == d["id"]
    # Invoices without a deal stay None
    assert _invoice(book, client)["deal_id"] is None


def test_payment_tx_stamps_deal_and_single_asset(brain, book, checking, client):
    d = _deal_with_assets(["asset-1"])
    made = _deal_invoice(book, client, d["id"])
    updated = inv.record_payment(
        "Alice",
        "business",
        book["id"],
        made["id"],
        {"amount_cents": 100_00, "account_id": checking["id"]},
        "Alice",
    )
    tx_id = updated["payments"][-1]["tx_id"]
    items, _total = fin.list_transactions("Alice", "business", book["id"])
    tx = next(t for t in items if t["id"] == tx_id)
    assert tx["deal_id"] == d["id"]
    assert tx["asset_id"] == "asset-1"  # exactly one linked asset → auto-linked


def test_payment_tx_no_asset_when_deal_has_zero_or_many(brain, book, checking, client):
    d = _deal_with_assets(["a1", "a2"])
    made = _deal_invoice(book, client, d["id"])
    updated = inv.record_payment(
        "Alice",
        "business",
        book["id"],
        made["id"],
        {"amount_cents": 50_00, "account_id": checking["id"]},
        "Alice",
    )
    items, _total = fin.list_transactions("Alice", "business", book["id"])
    tx = next(t for t in items if t["id"] == updated["payments"][-1]["tx_id"])
    assert tx["deal_id"] == d["id"]
    assert tx["asset_id"] is None  # ambiguous — user picks in the tx modal


def test_deal_invoices_scan_scoped_to_viewer(brain, book, client):
    d = _deal_with_assets([])
    _deal_invoice(book, client, d["id"])
    mine = inv.list_invoices_for_deal("Alice", "member", False, "business", d["id"])
    assert len(mine) == 1
    assert mine[0]["book_name"] == "LLC books"
    assert mine[0]["total_cents"] == 100_00
    # Another user must never see invoices from a book not visible to them
    assert inv.list_invoices_for_deal("Bob", "member", False, "business", d["id"]) == []
