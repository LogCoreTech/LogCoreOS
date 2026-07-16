"""Finance module Phase A: books, accounts, transactions, shards, balances, reports."""

import pytest

from services import finance_reports
from services import finance_service as svc
from services.file_service import finance_books_path, finance_tx_path


@pytest.fixture()
def book(brain):
    return svc.create_book("Alice", "personal", name="Family budget", created_by="Alice")


@pytest.fixture()
def checking(brain, book):
    return svc.add_account(
        "Alice",
        "personal",
        book["id"],
        {"name": "Checking", "type": "checking", "opening_balance_cents": 100_00},
    )


def _tx(account_id, amount, date="2026-07-01", category="", **kw):
    return {
        "date": date,
        "amount_cents": amount,
        "account_id": account_id,
        "category": category,
        **kw,
    }


# ---------------------------------------------------------------------------
# Books + workspace isolation
# ---------------------------------------------------------------------------


def test_create_book_defaults(brain, book):
    assert book["currency"] == "USD"
    assert any(c["name"] == "Groceries" for c in book["categories"])
    assert book["accounts"] == []
    assert not book["archived"]


def test_workspace_isolation(brain):
    svc.create_book("Alice", "personal", name="Personal", created_by="Alice")
    svc.create_book("Alice", "business", name="LLC books", created_by="Alice")

    personal = svc.list_books("Alice", "personal")
    business = svc.list_books("Alice", "business")
    assert [b["name"] for b in personal] == ["Personal"]
    assert [b["name"] for b in business] == ["LLC books"]
    # Physically separate files
    assert finance_books_path("Alice", "personal") != finance_books_path("Alice", "business")
    assert "Business" in str(finance_books_path("Alice", "business"))


def test_other_users_books_invisible(brain):
    other = svc.create_book("Bob", "personal", name="Bobs money", created_by="Bob")
    assert svc.find_book("Alice", "member", False, "personal", other["id"]) is None
    visible = svc.list_visible_books("Alice", "member", False, "personal")
    assert other["id"] not in [b["id"] for b in visible]


def test_pool_books_read_for_members_edit_for_admins(brain):
    pool_book = svc.create_book("_household", "personal", name="House fund", created_by="Admin")
    found_member = svc.find_book("Alice", "member", False, "personal", pool_book["id"])
    assert found_member is not None
    store, _b, access = found_member
    assert store == "_household"
    assert access == "read"

    _s, _b, admin_access = svc.find_book("Admin", "member", True, "personal", pool_book["id"])
    assert admin_access == "edit"

    annotated = svc.list_visible_books("Alice", "member", False, "personal")
    entry = next(b for b in annotated if b["id"] == pool_book["id"])
    assert entry["_owner"] == "household"
    assert entry["_access"] == "read"


def test_team_pool_scoped_to_business(brain):
    team_book = svc.create_book("_team", "business", name="Team ops", created_by="Admin")
    # Team pool files live at the pseudo-user's personal base path
    assert finance_books_path("_team", "personal").exists()
    # Visible in business workspace, not personal
    biz = svc.list_visible_books("Alice", "member", False, "business")
    assert team_book["id"] in [b["id"] for b in biz]
    personal = svc.list_visible_books("Alice", "member", False, "personal")
    assert team_book["id"] not in [b["id"] for b in personal]


def test_book_validation(brain):
    with pytest.raises(ValueError):
        svc.create_book("Alice", "personal", name="", created_by="Alice")
    with pytest.raises(ValueError):
        svc.create_book("Alice", "personal", name="X", created_by="Alice", currency="DOLLARS")
    with pytest.raises(ValueError):
        svc.create_book(
            "Alice",
            "personal",
            name="X",
            created_by="Alice",
            categories=[{"name": "A", "kind": "expense"}, {"name": "a", "kind": "income"}],
        )


# ---------------------------------------------------------------------------
# Transactions: cents integrity, shards, cross-year moves
# ---------------------------------------------------------------------------


def test_amount_must_be_integer_cents(brain, book, checking):
    for bad in (0, 45.99, "45", True, None):
        with pytest.raises(ValueError):
            svc.add_transaction("Alice", "personal", book, _tx(checking["id"], bad), "Alice")


def test_category_and_account_validation(brain, book, checking):
    with pytest.raises(ValueError):
        svc.add_transaction(
            "Alice", "personal", book, _tx(checking["id"], -100, category="Nope"), "Alice"
        )
    with pytest.raises(ValueError):
        svc.add_transaction("Alice", "personal", book, _tx("not-an-account", -100), "Alice")
    # Uncategorized ("") is always allowed
    tx = svc.add_transaction("Alice", "personal", book, _tx(checking["id"], -100), "Alice")
    assert tx["category"] == ""
    assert tx["created_by"] == "Alice"
    assert tx["source"] == "manual"


def test_transactions_shard_by_year(brain, book, checking):
    svc.add_transaction(
        "Alice", "personal", book, _tx(checking["id"], -500, date="2025-12-31"), "Alice"
    )
    svc.add_transaction(
        "Alice", "personal", book, _tx(checking["id"], -700, date="2026-01-01"), "Alice"
    )
    assert finance_tx_path("Alice", book["id"], 2025, "personal").exists()
    assert finance_tx_path("Alice", book["id"], 2026, "personal").exists()
    items, total = svc.list_transactions("Alice", "personal", book["id"])
    assert total == 2
    assert [t["date"] for t in items] == ["2026-01-01", "2025-12-31"]  # newest first


def test_cross_year_date_edit_moves_shards(brain, book, checking):
    tx = svc.add_transaction(
        "Alice", "personal", book, _tx(checking["id"], -500, date="2026-01-15"), "Alice"
    )
    updated = svc.update_transaction("Alice", "personal", book, tx["id"], {"date": "2025-11-30"})
    assert updated["date"] == "2025-11-30"
    shard_2026 = svc._read_shard("Alice", "personal", book["id"], 2026)
    shard_2025 = svc._read_shard("Alice", "personal", book["id"], 2025)
    assert shard_2026["transactions"] == []
    assert [t["id"] for t in shard_2025["transactions"]] == [tx["id"]]
    # Still findable and only once
    _items, total = svc.list_transactions("Alice", "personal", book["id"])
    assert total == 1


def test_transaction_filters(brain, book, checking):
    savings = svc.add_account(
        "Alice", "personal", book["id"], {"name": "Savings", "type": "savings"}
    )
    svc.add_transaction(
        "Alice",
        "personal",
        book,
        _tx(checking["id"], -4599, category="Groceries", payee="Kroger"),
        "Alice",
    )
    svc.add_transaction(
        "Alice", "personal", book, _tx(savings["id"], 250_000, category="Salary"), "Alice"
    )
    by_account, _ = svc.list_transactions("Alice", "personal", book["id"], account_id=savings["id"])
    assert len(by_account) == 1 and by_account[0]["amount_cents"] == 250_000
    by_cat, _ = svc.list_transactions("Alice", "personal", book["id"], category="Groceries")
    assert len(by_cat) == 1
    by_q, _ = svc.list_transactions("Alice", "personal", book["id"], query="kroger")
    assert len(by_q) == 1


def test_removing_category_relabels_transactions(brain, book, checking):
    svc.add_transaction(
        "Alice", "personal", book, _tx(checking["id"], -100, category="Dining"), "Alice"
    )
    new_cats = [c for c in book["categories"] if c["name"] != "Dining"]
    updated_book = svc.update_book("Alice", "personal", book["id"], {"categories": new_cats})
    assert not any(c["name"] == "Dining" for c in updated_book["categories"])
    items, _ = svc.list_transactions("Alice", "personal", book["id"])
    assert items[0]["category"] == ""


# ---------------------------------------------------------------------------
# Balances + net worth (always computed)
# ---------------------------------------------------------------------------


def test_balance_math(brain, book, checking):
    svc.add_transaction("Alice", "personal", book, _tx(checking["id"], 250_000), "Alice")
    svc.add_transaction("Alice", "personal", book, _tx(checking["id"], -45_99), "Alice")
    fresh = svc.get_book("Alice", "personal", book["id"])
    summary = svc.book_summary("Alice", "personal", fresh)
    assert summary["balances"][checking["id"]] == 100_00 + 250_000 - 45_99
    assert summary["total_cents"] == 100_00 + 250_000 - 45_99


def test_archived_account_excluded_from_total(brain, book, checking):
    cash = svc.add_account(
        "Alice",
        "personal",
        book["id"],
        {"name": "Cash", "type": "cash", "opening_balance_cents": 50_00},
    )
    svc.update_account("Alice", "personal", book["id"], cash["id"], {"archived": True})
    fresh = svc.get_book("Alice", "personal", book["id"])
    summary = svc.book_summary("Alice", "personal", fresh)
    assert summary["balances"][cash["id"]] == 50_00  # still computed
    assert summary["total_cents"] == 100_00  # but excluded from the rollup


def test_net_worth_across_own_and_pool(brain, book, checking):
    pool_book = svc.create_book("_household", "personal", name="House", created_by="Admin")
    svc.add_account(
        "_household",
        "personal",
        pool_book["id"],
        {"name": "Joint", "type": "checking", "opening_balance_cents": 300_00},
    )
    result = finance_reports.net_worth("Alice", "member", False, "personal")
    assert result["total_cents"] == 100_00 + 300_00
    assert len(result["books"]) == 2


# ---------------------------------------------------------------------------
# Accounts lifecycle
# ---------------------------------------------------------------------------


def test_account_delete_blocked_with_transactions(brain, book, checking):
    svc.add_transaction("Alice", "personal", book, _tx(checking["id"], -100), "Alice")
    assert svc.account_has_transactions("Alice", "personal", book["id"], checking["id"])
    empty = svc.add_account("Alice", "personal", book["id"], {"name": "Empty", "type": "cash"})
    assert not svc.account_has_transactions("Alice", "personal", book["id"], empty["id"])
    assert svc.delete_account("Alice", "personal", book["id"], empty["id"])


def test_archived_account_rejects_new_transactions(brain, book, checking):
    svc.update_account("Alice", "personal", book["id"], checking["id"], {"archived": True})
    fresh = svc.get_book("Alice", "personal", book["id"])
    with pytest.raises(ValueError):
        svc.add_transaction("Alice", "personal", fresh, _tx(checking["id"], -100), "Alice")


def test_delete_book_removes_shard_dir(brain, book, checking):
    svc.add_transaction("Alice", "personal", book, _tx(checking["id"], -100), "Alice")
    assert svc.has_transactions("Alice", "personal", book["id"])
    assert svc.delete_book("Alice", "personal", book["id"])
    assert svc.list_books("Alice", "personal") == []
    assert not finance_tx_path("Alice", book["id"], 2026, "personal").parent.exists()


# ---------------------------------------------------------------------------
# Monthly report
# ---------------------------------------------------------------------------


def test_monthly_report_math(brain, book, checking):
    svc.add_transaction(
        "Alice",
        "personal",
        book,
        _tx(checking["id"], 250_000, date="2026-07-01", category="Salary"),
        "Alice",
    )
    svc.add_transaction(
        "Alice",
        "personal",
        book,
        _tx(checking["id"], -45_99, date="2026-07-05", category="Groceries"),
        "Alice",
    )
    svc.add_transaction(
        "Alice",
        "personal",
        book,
        _tx(checking["id"], -20_00, date="2026-07-08", category="Groceries"),
        "Alice",
    )
    # Different month — must not appear
    svc.add_transaction(
        "Alice",
        "personal",
        book,
        _tx(checking["id"], -999_99, date="2026-06-30", category="Shopping"),
        "Alice",
    )
    report = finance_reports.monthly_report("Alice", "personal", book, "2026-07")
    assert report["income_cents"] == 250_000
    assert report["expense_cents"] == -(45_99 + 20_00)
    assert report["net_cents"] == 250_000 - 45_99 - 20_00
    assert report["transaction_count"] == 3
    groceries = next(c for c in report["categories"] if c["category"] == "Groceries")
    assert groceries["expense_cents"] == -(45_99 + 20_00)
    assert groceries["count"] == 2

    with pytest.raises(ValueError):
        finance_reports.monthly_report("Alice", "personal", book, "July 2026")


# ---------------------------------------------------------------------------
# Guest role default + m007
# ---------------------------------------------------------------------------


def test_guest_role_finance_disabled_by_default(brain):
    from services.features_service import get_effective_disabled

    assert "finance" in get_effective_disabled("guest", [])
    assert "finance" not in get_effective_disabled("member", [])


def test_m007_disables_finance_for_existing_guest_role(brain):
    from migrations.runner import m007_finance_guest_disabled
    from services.file_service import read_json, write_json

    features_file = brain / "_system" / "features.json"
    write_json(
        features_file,
        {"profile": "personal", "roles": {"member": {"tasks": True}, "guest": {"tasks": True}}},
    )
    m007_finance_guest_disabled(brain)
    data = read_json(features_file)
    assert data["roles"]["guest"]["finance"] is False
    assert "finance" not in data["roles"]["member"]  # member untouched

    # Idempotent — an admin re-enabling finance for guests must stick
    data["roles"]["guest"]["finance"] = True
    write_json(features_file, data)
    m007_finance_guest_disabled(brain)
    assert read_json(features_file)["roles"]["guest"]["finance"] is True


# ---------------------------------------------------------------------------
# Workspace-aware seed categories + tax buckets (Phase 1 items 5 & 9)
# ---------------------------------------------------------------------------


def test_personal_book_seed_defaults(brain):
    b = svc.create_book("Alice", "personal", name="Home", created_by="Alice")
    names = {c["name"] for c in b["categories"]}
    assert "Groceries" in names and "Salary" in names
    assert "Payroll" not in names  # business-only bucket
    # Personal tax buckets
    assert "Medical" in b["tax_categories"]
    assert "Home Office" not in b["tax_categories"]


def test_business_book_seed_defaults(brain):
    b = svc.create_book("Alice", "business", name="LogCore", created_by="Alice")
    names = {c["name"] for c in b["categories"]}
    assert "Payroll" in names and "Product Sales" in names
    assert "Groceries" not in names
    # Business tax buckets (Schedule-C flavored)
    assert "Home Office" in b["tax_categories"]
    assert "Medical" not in b["tax_categories"]
