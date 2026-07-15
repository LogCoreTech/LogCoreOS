"""Finance Phase C: budgets + alerts, recurring + matching, planned, projection, deviation."""

from datetime import date, timedelta

import pytest

from services import finance_planning_service as plan
from services import finance_service as fin


@pytest.fixture()
def book(brain):
    return fin.create_book("Alice", "personal", name="Family budget", created_by="Alice")


@pytest.fixture()
def checking(brain, book):
    return fin.add_account(
        "Alice",
        "personal",
        book["id"],
        {"name": "Checking", "type": "checking", "opening_balance_cents": 100_00},
    )


@pytest.fixture()
def notify_log(monkeypatch):
    """Capture finance notifications as (recipient, title) tuples."""
    sent = []

    def fake_notify(recipients, title, body, book_id):
        for r in recipients:
            sent.append((r, title))

    monkeypatch.setattr(plan, "_notify", fake_notify)
    return sent


def _fresh(book):
    return fin.get_book("Alice", "personal", book["id"])


def _spend(book, checking, cents, day="2026-07-05", category="Groceries"):
    return fin.add_transaction(
        "Alice",
        "personal",
        book,
        {
            "date": day,
            "amount_cents": -cents,
            "account_id": checking["id"],
            "category": category,
        },
        "Alice",
    )


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def test_budget_status_math(brain, book, checking):
    plan.set_budgets(
        "Alice", "personal", book, [{"category": "Groceries", "monthly_limit_cents": 10_00}]
    )
    _spend(book, checking, 9_00)
    status = plan.budget_status("Alice", "personal", _fresh(book), "2026-07")
    assert status[0]["spent_cents"] == 9_00
    assert status[0]["remaining_cents"] == 1_00
    assert status[0]["pct"] == 90


def test_budget_validation(brain, book):
    with pytest.raises(ValueError):
        plan.set_budgets(
            "Alice", "personal", book, [{"category": "Nope", "monthly_limit_cents": 100}]
        )
    with pytest.raises(ValueError):
        plan.set_budgets(
            "Alice", "personal", book, [{"category": "Groceries", "monthly_limit_cents": 0}]
        )


def test_budget_alerts_escalate_without_duplicates(brain, book, checking, notify_log):
    plan.set_budgets(
        "Alice", "personal", book, [{"category": "Groceries", "monthly_limit_cents": 10_00}]
    )
    # 90% → warn
    _spend(book, checking, 9_00)
    plan.check_budget_alerts("Alice", "personal", _fresh(book), "2026-07")
    assert len(notify_log) == 1 and "warning" in notify_log[0][1].lower()
    # Re-check, no change → no duplicate
    plan.check_budget_alerts("Alice", "personal", _fresh(book), "2026-07")
    assert len(notify_log) == 1
    # +$2 → over
    _spend(book, checking, 2_00)
    plan.check_budget_alerts("Alice", "personal", _fresh(book), "2026-07")
    assert len(notify_log) == 2 and "over budget" in notify_log[1][1].lower()
    # Re-check again → still no duplicate
    plan.check_budget_alerts("Alice", "personal", _fresh(book), "2026-07")
    assert len(notify_log) == 2


def test_pool_budget_alerts_go_to_admins(brain, notify_log, monkeypatch):
    from services import auth_service

    monkeypatch.setattr(
        auth_service,
        "list_users",
        lambda: [{"name": "Boss", "role": "admin"}, {"name": "Kid", "role": "member"}],
    )
    pool_book = fin.create_book("_household", "personal", name="House", created_by="Boss")
    acct = fin.add_account(
        "_household", "personal", pool_book["id"], {"name": "Joint", "type": "checking"}
    )
    plan.set_budgets(
        "_household",
        "personal",
        pool_book,
        [{"category": "Groceries", "monthly_limit_cents": 10_00}],
    )
    fin.add_transaction(
        "_household",
        "personal",
        pool_book,
        {
            "date": "2026-07-05",
            "amount_cents": -11_00,
            "account_id": acct["id"],
            "category": "Groceries",
        },
        "Boss",
    )
    fresh = fin.get_book("_household", "personal", pool_book["id"])
    plan.check_budget_alerts("_household", "personal", fresh, "2026-07")
    assert [r for r, _t in notify_log] == ["Boss"]


# ---------------------------------------------------------------------------
# Recurring: cadence + matching + missed
# ---------------------------------------------------------------------------


def test_advance_due_cadences():
    assert plan.advance_due("2026-07-05", "weekly") == "2026-07-12"
    assert plan.advance_due("2026-01-31", "monthly") == "2026-02-28"  # clamps
    assert plan.advance_due("2024-02-29", "yearly") == "2025-02-28"  # leap clamp
    assert plan.advance_due("2026-12-15", "monthly") == "2027-01-15"


def test_bill_matching_advances_due(brain, book, checking):
    item = plan.add_recurring(
        "Alice",
        "personal",
        book,
        {
            "name": "Netflix",
            "amount_cents": -15_99,
            "account_id": checking["id"],
            "category": "",
            "cadence": "monthly",
            "next_due": "2026-07-15",
        },
        "Alice",
    )
    # Amount within 3%/$2 tolerance, date within 4 days → match
    tx = _spend(book, checking, 16_49, day="2026-07-17", category="")
    matched = plan.match_bill("Alice", "personal", _fresh(book), tx)
    assert matched and matched["id"] == item["id"]
    items = plan.list_recurring("Alice", "personal", book["id"])
    assert items[0]["last_paid"] == "2026-07-17"
    assert items[0]["next_due"] == "2026-08-15"


def test_bill_matching_rejects_wrong_amount_or_date(brain, book, checking):
    plan.add_recurring(
        "Alice",
        "personal",
        book,
        {
            "name": "Rent",
            "amount_cents": -1200_00,
            "account_id": checking["id"],
            "category": "",
            "cadence": "monthly",
            "next_due": "2026-07-01",
        },
        "Alice",
    )
    # Amount off by far more than tolerance
    tx = _spend(book, checking, 600_00, day="2026-07-01", category="")
    assert plan.match_bill("Alice", "personal", _fresh(book), tx) is None
    # Right amount, date too far away
    tx2 = _spend(book, checking, 1200_00, day="2026-07-20", category="")
    assert plan.match_bill("Alice", "personal", _fresh(book), tx2) is None


def test_missed_bills_notify_once(brain, book, checking, notify_log):
    past_due = (date.today() - timedelta(days=10)).isoformat()
    plan.add_recurring(
        "Alice",
        "personal",
        book,
        {
            "name": "Insurance",
            "amount_cents": -80_00,
            "account_id": checking["id"],
            "category": "",
            "cadence": "monthly",
            "next_due": past_due,
        },
        "Alice",
    )
    plan.check_missed_bills("Alice", "personal", _fresh(book))
    plan.check_missed_bills("Alice", "personal", _fresh(book))
    assert len(notify_log) == 1
    assert "missed bill" in notify_log[0][1].lower()
    result = plan.upcoming_recurring("Alice", "personal", book["id"])
    assert len(result["missed"]) == 1


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def test_projection_includes_recurring_and_planned(brain, book, checking):
    today = date.today()
    in_3 = (today + timedelta(days=3)).isoformat()
    in_5 = (today + timedelta(days=5)).isoformat()
    plan.add_recurring(
        "Alice",
        "personal",
        book,
        {
            "name": "Netflix",
            "amount_cents": -15_99,
            "account_id": checking["id"],
            "category": "",
            "cadence": "monthly",
            "next_due": in_3,
        },
        "Alice",
    )
    plan.add_planned(
        "Alice",
        "personal",
        book,
        {"name": "Sell mower", "date": in_5, "amount_cents": 200_00, "account_id": checking["id"]},
        "Alice",
    )
    result = plan.project_balance(
        "Alice", "personal", _fresh(book), checking["id"], (today + timedelta(days=7)).isoformat()
    )
    assert result["current_cents"] == 100_00
    assert result["projected_cents"] == 100_00 - 15_99 + 200_00
    assert [i["source"] for i in result["items"]] == ["recurring", "planned"]

    # Done planned items and past-horizon recurring are excluded
    result_short = plan.project_balance(
        "Alice", "personal", _fresh(book), checking["id"], (today + timedelta(days=1)).isoformat()
    )
    assert result_short["projected_cents"] == 100_00


def test_projection_expands_weekly_occurrences(brain, book, checking):
    today = date.today()
    plan.add_recurring(
        "Alice",
        "personal",
        book,
        {
            "name": "Cleaner",
            "amount_cents": -50_00,
            "account_id": checking["id"],
            "category": "",
            "cadence": "weekly",
            "next_due": (today + timedelta(days=2)).isoformat(),
        },
        "Alice",
    )
    result = plan.project_balance(
        "Alice", "personal", _fresh(book), checking["id"], (today + timedelta(days=16)).isoformat()
    )
    assert len(result["items"]) == 3  # days +2, +9, +16
    assert result["projected_cents"] == 100_00 - 3 * 50_00


# ---------------------------------------------------------------------------
# Deviation
# ---------------------------------------------------------------------------


def test_deviation_alert_fires_and_dedups(brain, book, checking, notify_log):
    fin.update_account(
        "Alice",
        "personal",
        book["id"],
        checking["id"],
        {"deviation_threshold_cents": 1_00, "synced_balance_cents": 94_00},
    )
    # Ledger balance 100.00 vs bank 94.00 → $6 drift > $1 threshold
    plan.check_deviation("Alice", "personal", _fresh(book))
    assert len(notify_log) == 1
    assert "deviation" in notify_log[0][1].lower()
    # Same day, same delta → deduped
    plan.check_deviation("Alice", "personal", _fresh(book))
    assert len(notify_log) == 1
    # Same day but delta changed >10% → re-alert
    fin.update_account(
        "Alice", "personal", book["id"], checking["id"], {"synced_balance_cents": 50_00}
    )
    plan.check_deviation("Alice", "personal", _fresh(book))
    assert len(notify_log) == 2


def test_deviation_skips_without_threshold_or_balance(brain, book, checking, notify_log):
    # No threshold set
    fin.update_account("Alice", "personal", book["id"], checking["id"], {"synced_balance_cents": 0})
    plan.check_deviation("Alice", "personal", _fresh(book))
    # Threshold but no synced balance
    cash = fin.add_account("Alice", "personal", book["id"], {"name": "Cash", "type": "cash"})
    fin.update_account(
        "Alice", "personal", book["id"], cash["id"], {"deviation_threshold_cents": 1_00}
    )
    plan.check_deviation("Alice", "personal", _fresh(book))
    assert notify_log == []


def test_within_threshold_no_alert(brain, book, checking, notify_log):
    fin.update_account(
        "Alice",
        "personal",
        book["id"],
        checking["id"],
        {"deviation_threshold_cents": 10_00, "synced_balance_cents": 95_00},
    )
    plan.check_deviation("Alice", "personal", _fresh(book))
    assert notify_log == []


# ---------------------------------------------------------------------------
# Write-path hook
# ---------------------------------------------------------------------------


def test_on_transactions_added_matches_and_alerts(brain, book, checking, notify_log):
    plan.set_budgets(
        "Alice", "personal", book, [{"category": "Groceries", "monthly_limit_cents": 5_00}]
    )
    plan.add_recurring(
        "Alice",
        "personal",
        book,
        {
            "name": "Box sub",
            "amount_cents": -6_00,
            "account_id": checking["id"],
            "category": "Groceries",
            "cadence": "monthly",
            "next_due": "2026-07-05",
        },
        "Alice",
    )
    tx = _spend(book, checking, 6_00, day="2026-07-05")
    plan.on_transactions_added("Alice", "personal", book["id"], [tx])
    # Bill matched + budget went straight to over
    items = plan.list_recurring("Alice", "personal", book["id"])
    assert items[0]["last_paid"] == "2026-07-05"
    assert any("over budget" in t.lower() for _r, t in notify_log)


# ---------------------------------------------------------------------------
# Tax flags on recurring + planned (Phase 1 items 10 & 11)
# ---------------------------------------------------------------------------


def test_recurring_accepts_and_defaults_tax_flags(brain, book, checking):
    item = plan.add_recurring(
        "Alice",
        "personal",
        book,
        {
            "name": "Office rent",
            "amount_cents": -500_00,
            "account_id": checking["id"],
            "category": "",
            "cadence": "monthly",
            "next_due": "2026-07-15",
            "deductible": True,
            "tax_category": "Business Expense",
        },
        "Alice",
    )
    assert item["deductible"] is True
    assert item["tax_category"] == "Business Expense"
    # Defaults when omitted
    plain = plan.add_recurring(
        "Alice",
        "personal",
        book,
        {
            "name": "Netflix",
            "amount_cents": -15_99,
            "account_id": checking["id"],
            "category": "",
            "cadence": "monthly",
            "next_due": "2026-07-20",
        },
        "Alice",
    )
    assert plain["deductible"] is False
    assert plain["tax_category"] is None


def test_recurring_rejects_unknown_tax_bucket(brain, book, checking):
    with pytest.raises(ValueError):
        plan.add_recurring(
            "Alice",
            "personal",
            book,
            {
                "name": "Bad bucket",
                "amount_cents": -10_00,
                "account_id": checking["id"],
                "cadence": "monthly",
                "next_due": "2026-07-15",
                "tax_category": "Not A Real Bucket",
            },
            "Alice",
        )


def test_planned_accepts_tax_flags(brain, book, checking):
    item = plan.add_planned(
        "Alice",
        "personal",
        book,
        {
            "name": "Annual license",
            "date": "2026-08-01",
            "amount_cents": -300_00,
            "account_id": checking["id"],
            "deductible": True,
            "tax_category": "Business Expense",
        },
        "Alice",
    )
    assert item["deductible"] is True
    assert item["tax_category"] == "Business Expense"


def test_bill_match_propagates_tax_flags_to_tx(brain, book, checking):
    plan.add_recurring(
        "Alice",
        "personal",
        book,
        {
            "name": "Office rent",
            "amount_cents": -500_00,
            "account_id": checking["id"],
            "category": "",
            "cadence": "monthly",
            "next_due": "2026-07-15",
            "deductible": True,
            "tax_category": "Business Expense",
        },
        "Alice",
    )
    tx = _spend(book, checking, 500_00, day="2026-07-16", category="")
    assert tx.get("deductible") is False
    plan.match_bill("Alice", "personal", _fresh(book), tx)
    items, _ = fin.list_transactions("Alice", "personal", book["id"])
    saved = next(t for t in items if t["id"] == tx["id"])
    assert saved["deductible"] is True
    assert saved["tax_category"] == "Business Expense"
