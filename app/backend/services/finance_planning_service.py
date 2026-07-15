"""Finance planning: budgets + alerts, recurring bills, planned items,
projected balances and deviation alerts.

All projections/statuses are computed on read. The only stored state besides
the user's own items is notification-dedup bookkeeping (`alert_state` on
budgets, `missed_notified_for` on recurring items, `last_deviation_alert`
on accounts) — operational data, not derived values.

The projected balance for a future date is:
    computed current balance
  + every recurring occurrence between today and that date
  + every not-done planned item in that range
The deviation check compares the bank-reported balance (synced_balance_cents)
against the computed ledger balance — a drift bigger than the account's
threshold means unrecorded (possibly fraudulent) activity.
"""

import calendar
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from services import finance_service
from services.file_service import finance_book_dir, read_json, write_json

logger = logging.getLogger("logcore.finance")

CADENCES = {"weekly", "monthly", "yearly"}
_MATCH_DATE_TOLERANCE_DAYS = 4
_MISSED_AFTER_DAYS = 3
_MAX_PROJECTION_ITEMS = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _book_file(store_user: str, workspace: str, book_id: str, name: str):
    ws = finance_service.store_workspace(store_user, workspace)
    return finance_book_dir(store_user, book_id, ws) / name


# ---------------------------------------------------------------------------
# Alert recipients — own books notify the owner; pool books notify admins
# ---------------------------------------------------------------------------


def _alert_recipients(store_user: str) -> list[str]:
    if not finance_service.is_pool(store_user):
        return [store_user]
    try:
        from services import auth_service

        return [u["name"] for u in auth_service.list_users() if u.get("role") == "admin"]
    except Exception:
        return []


def _notify(recipients: list[str], title: str, body: str, book_id: str) -> None:
    try:
        from services.suggestions_service import notify_user

        for name in recipients:
            notify_user(
                name,
                title,
                body,
                source="finance",
                action={"type": "open_finance_book", "book_id": book_id},
                url=f"/finance?book={book_id}",
            )
    except Exception:
        logger.exception("finance alert delivery failed")


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def get_budgets(store_user: str, workspace: str, book_id: str) -> dict:
    return read_json(
        _book_file(store_user, workspace, book_id, "budgets.json"),
        default={"budgets": [], "alert_state": {}},
    )


def set_budgets(store_user: str, workspace: str, book: dict, budgets: list[dict]) -> list[dict]:
    book = finance_service.fresh_book(store_user, workspace, book)
    valid_categories = {c["name"] for c in book.get("categories", [])}
    cleaned = []
    seen = set()
    for b in budgets:
        category = b.get("category") or ""
        limit = b.get("monthly_limit_cents")
        if category not in valid_categories:
            raise ValueError(f"Unknown category: {category!r}")
        if category in seen:
            raise ValueError(f"Duplicate budget for {category}")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("monthly_limit_cents must be a positive integer")
        seen.add(category)
        cleaned.append({"category": category, "monthly_limit_cents": limit})
    data = get_budgets(store_user, workspace, book["id"])
    data["budgets"] = cleaned
    write_json(_book_file(store_user, workspace, book["id"], "budgets.json"), data)
    return cleaned


def budget_status(store_user: str, workspace: str, book: dict, month: str) -> list[dict]:
    """Spent/remaining/pct per budgeted category for one month — computed on read."""
    book = finance_service.fresh_book(store_user, workspace, book)
    budgets = get_budgets(store_user, workspace, book["id"]).get("budgets", [])
    if not budgets:
        return []
    from services.finance_reports import month_end

    items, _total = finance_service.list_transactions(
        store_user,
        workspace,
        book["id"],
        date_from=f"{month}-01",
        date_to=month_end(int(month[:4]), int(month[5:7])),
        limit=100000,
    )
    spent_by_cat: dict[str, int] = {}
    for t in items:
        if t["amount_cents"] < 0:
            cat = t.get("category") or ""
            spent_by_cat[cat] = spent_by_cat.get(cat, 0) - t["amount_cents"]
    out = []
    for b in budgets:
        spent = spent_by_cat.get(b["category"], 0)
        limit = b["monthly_limit_cents"]
        out.append(
            {
                "category": b["category"],
                "monthly_limit_cents": limit,
                "spent_cents": spent,
                "remaining_cents": limit - spent,
                "pct": round(spent * 100 / limit) if limit else 0,
            }
        )
    return out


def check_budget_alerts(store_user: str, workspace: str, book: dict, month: str) -> None:
    """Notify on none→warn and →over escalations, once per state per month."""
    book = finance_service.fresh_book(store_user, workspace, book)
    data = get_budgets(store_user, workspace, book["id"])
    if not data.get("budgets"):
        return
    warn_pct = book.get("budget_warn_pct", 80)
    state = data.setdefault("alert_state", {}).setdefault(month, {})
    changed = False
    for status in budget_status(store_user, workspace, book, month):
        cat, pct = status["category"], status["pct"]
        new_state = "over" if pct >= 100 else "warn" if pct >= warn_pct else None
        old_state = state.get(cat)
        if new_state == old_state or new_state is None:
            continue
        if old_state == "over":
            continue  # never downgrade or repeat after "over"
        state[cat] = new_state
        changed = True
        if new_state == "over":
            title = f"🔴 Over budget: {cat}"
            body = (
                f"{book['name']}: {cat} is at {pct}% — "
                f"{_fmt(status['spent_cents'])} of {_fmt(status['monthly_limit_cents'])} spent."
            )
        else:
            title = f"🟡 Budget warning: {cat}"
            body = (
                f"{book['name']}: {cat} hit {pct}% of its {_fmt(status['monthly_limit_cents'])} "
                f"budget ({_fmt(status['remaining_cents'])} left)."
            )
        _notify(_alert_recipients(store_user), title, body, book["id"])
    if changed:
        write_json(_book_file(store_user, workspace, book["id"], "budgets.json"), data)


def _fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


# ---------------------------------------------------------------------------
# Recurring bills & subscriptions
# ---------------------------------------------------------------------------


def list_recurring(store_user: str, workspace: str, book_id: str) -> list[dict]:
    return read_json(
        _book_file(store_user, workspace, book_id, "recurring.json"), default={"items": []}
    ).get("items", [])


def _save_recurring(store_user: str, workspace: str, book_id: str, items: list[dict]) -> None:
    write_json(_book_file(store_user, workspace, book_id, "recurring.json"), {"items": items})


def _validate_recurring(book: dict, data: dict, partial: bool = False) -> dict:
    out: dict = {}
    if "name" in data or not partial:
        name = (data.get("name") or "").strip()
        if not name or len(name) > 80:
            raise ValueError("Recurring item name must be 1-80 characters")
        out["name"] = name
    if "amount_cents" in data or not partial:
        amount = data.get("amount_cents")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount == 0:
            raise ValueError("amount_cents must be a non-zero integer")
        out["amount_cents"] = amount
    if "account_id" in data or not partial:
        account = next(
            (a for a in book.get("accounts", []) if a["id"] == data.get("account_id")), None
        )
        if not account:
            raise ValueError("Unknown account")
        out["account_id"] = account["id"]
    if "category" in data or not partial:
        category = data.get("category", "")
        if category and not any(c["name"] == category for c in book.get("categories", [])):
            raise ValueError(f"Unknown category: {category!r}")
        out["category"] = category
    if "cadence" in data or not partial:
        cadence = data.get("cadence", "monthly")
        if cadence not in CADENCES:
            raise ValueError(f"Invalid cadence: {cadence!r}")
        out["cadence"] = cadence
    if "next_due" in data or not partial:
        try:
            out["next_due"] = date.fromisoformat(data.get("next_due") or "").isoformat()
        except (TypeError, ValueError):
            raise ValueError("next_due must be YYYY-MM-DD")
    if "autopay" in data:
        out["autopay"] = bool(data["autopay"])
    if "active" in data:
        out["active"] = bool(data["active"])
    if "deductible" in data:
        out["deductible"] = bool(data["deductible"])
    if "tax_category" in data:
        tc = (data.get("tax_category") or "").strip()
        if tc and tc not in book.get("tax_categories", []):
            raise ValueError(f"Unknown tax bucket: {tc!r}")
        out["tax_category"] = tc or None
    return out


def add_recurring(store_user: str, workspace: str, book: dict, data: dict, created_by: str) -> dict:
    book = finance_service.fresh_book(store_user, workspace, book)
    fields = _validate_recurring(book, data)
    item = {
        "id": str(uuid.uuid4()),
        "autopay": bool(data.get("autopay", False)),
        "active": True,
        "last_paid": None,
        "missed_notified_for": None,
        "deductible": False,
        "tax_category": None,
        "created_by": created_by,
        "created_at": _now(),
        **fields,
    }
    items = list_recurring(store_user, workspace, book["id"])
    items.append(item)
    _save_recurring(store_user, workspace, book["id"], items)
    return item


def update_recurring(
    store_user: str, workspace: str, book: dict, item_id: str, updates: dict
) -> dict | None:
    book = finance_service.fresh_book(store_user, workspace, book)
    items = list_recurring(store_user, workspace, book["id"])
    for i, item in enumerate(items):
        if item["id"] != item_id:
            continue
        fields = _validate_recurring(book, updates, partial=True)
        if "next_due" in fields:
            fields["missed_notified_for"] = None
        items[i] = {**item, **fields}
        _save_recurring(store_user, workspace, book["id"], items)
        return items[i]
    return None


def delete_recurring(store_user: str, workspace: str, book_id: str, item_id: str) -> bool:
    items = list_recurring(store_user, workspace, book_id)
    remaining = [i for i in items if i["id"] != item_id]
    if len(remaining) == len(items):
        return False
    _save_recurring(store_user, workspace, book_id, remaining)
    return True


def advance_due(next_due: str, cadence: str) -> str:
    """Next occurrence after next_due. Monthly/yearly clamp to month end."""
    d = date.fromisoformat(next_due)
    if cadence == "weekly":
        return (d + timedelta(days=7)).isoformat()
    if cadence == "monthly":
        year, month = (d.year, d.month + 1) if d.month < 12 else (d.year + 1, 1)
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day).isoformat()
    # yearly
    year = d.year + 1
    day = min(d.day, calendar.monthrange(year, d.month)[1])
    return date(year, d.month, day).isoformat()


def match_bill(store_user: str, workspace: str, book: dict, tx: dict) -> dict | None:
    """If a landing transaction pays a recurring bill, mark it and advance.

    Match: same account, same sign, amount within ±max(3%, $2), date within
    ±4 days of next_due."""
    items = list_recurring(store_user, workspace, book["id"])
    tx_amount = tx.get("amount_cents", 0)
    tx_date = date.fromisoformat(tx["date"])
    for i, item in enumerate(items):
        if not item.get("active", True) or item.get("account_id") != tx.get("account_id"):
            continue
        expected = item["amount_cents"]
        if (expected > 0) != (tx_amount > 0):
            continue
        tolerance = max(abs(expected) * 3 // 100, 200)
        if abs(tx_amount - expected) > tolerance:
            continue
        try:
            due = date.fromisoformat(item["next_due"])
        except (TypeError, ValueError):
            continue
        if abs((tx_date - due).days) > _MATCH_DATE_TOLERANCE_DAYS:
            continue
        item["last_paid"] = tx["date"]
        item["next_due"] = advance_due(item["next_due"], item.get("cadence", "monthly"))
        item["missed_notified_for"] = None
        items[i] = item
        _save_recurring(store_user, workspace, book["id"], items)
        # Carry the recurring item's tax flags onto the matched tx if it lacks them.
        prop: dict = {}
        if item.get("deductible") and not tx.get("deductible"):
            prop["deductible"] = True
        if item.get("tax_category") and not tx.get("tax_category"):
            prop["tax_category"] = item["tax_category"]
        if prop:
            try:
                finance_service.update_transaction(
                    store_user, workspace, book["id"], tx["id"], prop
                )
            except Exception:
                logger.exception("recurring tax propagation failed")
        return item
    return None


def upcoming_recurring(store_user: str, workspace: str, book_id: str, days: int = 30) -> dict:
    """Upcoming + missed bills for the UI."""
    today = date.today()
    horizon = today + timedelta(days=days)
    upcoming = []
    missed = []
    for item in list_recurring(store_user, workspace, book_id):
        if not item.get("active", True):
            continue
        try:
            due = date.fromisoformat(item["next_due"])
        except (TypeError, ValueError):
            continue
        if due < today - timedelta(days=_MISSED_AFTER_DAYS):
            missed.append(item)
        elif due <= horizon:
            upcoming.append(item)
    upcoming.sort(key=lambda i: i["next_due"])
    missed.sort(key=lambda i: i["next_due"])
    return {"upcoming": upcoming, "missed": missed}


def check_missed_bills(store_user: str, workspace: str, book: dict) -> None:
    """Nightly: notify once per missed due date per item."""
    items = list_recurring(store_user, workspace, book["id"])
    today = date.today()
    changed = False
    for i, item in enumerate(items):
        if not item.get("active", True):
            continue
        try:
            due = date.fromisoformat(item["next_due"])
        except (TypeError, ValueError):
            continue
        if due >= today - timedelta(days=_MISSED_AFTER_DAYS):
            continue
        if item.get("missed_notified_for") == item["next_due"]:
            continue
        item["missed_notified_for"] = item["next_due"]
        items[i] = item
        changed = True
        _notify(
            _alert_recipients(store_user),
            f"⚠️ Missed bill: {item['name']}",
            f"{book['name']}: {item['name']} ({_fmt(item['amount_cents'])}) was due "
            f"{item['next_due']} and no matching transaction arrived.",
            book["id"],
        )
    if changed:
        _save_recurring(store_user, workspace, book["id"], items)


# ---------------------------------------------------------------------------
# Planned one-off items
# ---------------------------------------------------------------------------


def list_planned(store_user: str, workspace: str, book_id: str) -> list[dict]:
    return read_json(
        _book_file(store_user, workspace, book_id, "planned.json"), default={"items": []}
    ).get("items", [])


def _save_planned(store_user: str, workspace: str, book_id: str, items: list[dict]) -> None:
    write_json(_book_file(store_user, workspace, book_id, "planned.json"), {"items": items})


def add_planned(store_user: str, workspace: str, book: dict, data: dict, created_by: str) -> dict:
    book = finance_service.fresh_book(store_user, workspace, book)
    name = (data.get("name") or "").strip()
    if not name or len(name) > 80:
        raise ValueError("Planned item name must be 1-80 characters")
    amount = data.get("amount_cents")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount == 0:
        raise ValueError("amount_cents must be a non-zero integer")
    if not any(a["id"] == data.get("account_id") for a in book.get("accounts", [])):
        raise ValueError("Unknown account")
    try:
        item_date = date.fromisoformat(data.get("date") or "").isoformat()
    except (TypeError, ValueError):
        raise ValueError("date must be YYYY-MM-DD")
    deductible = bool(data.get("deductible", False))
    tax_category = (data.get("tax_category") or "").strip() or None
    if tax_category and tax_category not in book.get("tax_categories", []):
        raise ValueError(f"Unknown tax bucket: {tax_category!r}")
    item = {
        "id": str(uuid.uuid4()),
        "name": name,
        "date": item_date,
        "amount_cents": amount,
        "account_id": data["account_id"],
        "done": False,
        "deductible": deductible,
        "tax_category": tax_category,
        "created_by": created_by,
        "created_at": _now(),
    }
    items = list_planned(store_user, workspace, book["id"])
    items.append(item)
    _save_planned(store_user, workspace, book["id"], items)
    return item


def update_planned(
    store_user: str, workspace: str, book: dict, item_id: str, updates: dict
) -> dict | None:
    book = finance_service.fresh_book(store_user, workspace, book)
    items = list_planned(store_user, workspace, book["id"])
    for i, item in enumerate(items):
        if item["id"] != item_id:
            continue
        allowed: dict = {}
        if "name" in updates:
            name = (updates["name"] or "").strip()
            if not name or len(name) > 80:
                raise ValueError("Planned item name must be 1-80 characters")
            allowed["name"] = name
        if "amount_cents" in updates:
            amount = updates["amount_cents"]
            if isinstance(amount, bool) or not isinstance(amount, int) or amount == 0:
                raise ValueError("amount_cents must be a non-zero integer")
            allowed["amount_cents"] = amount
        if "date" in updates:
            try:
                allowed["date"] = date.fromisoformat(updates["date"] or "").isoformat()
            except (TypeError, ValueError):
                raise ValueError("date must be YYYY-MM-DD")
        if "account_id" in updates:
            if not any(a["id"] == updates["account_id"] for a in book.get("accounts", [])):
                raise ValueError("Unknown account")
            allowed["account_id"] = updates["account_id"]
        if "done" in updates:
            allowed["done"] = bool(updates["done"])
        if "deductible" in updates:
            allowed["deductible"] = bool(updates["deductible"])
        if "tax_category" in updates:
            tc = (updates["tax_category"] or "").strip() or None
            if tc and tc not in book.get("tax_categories", []):
                raise ValueError(f"Unknown tax bucket: {tc!r}")
            allowed["tax_category"] = tc
        items[i] = {**item, **allowed}
        _save_planned(store_user, workspace, book["id"], items)
        return items[i]
    return None


def delete_planned(store_user: str, workspace: str, book_id: str, item_id: str) -> bool:
    items = list_planned(store_user, workspace, book_id)
    remaining = [i for i in items if i["id"] != item_id]
    if len(remaining) == len(items):
        return False
    _save_planned(store_user, workspace, book_id, remaining)
    return True


# ---------------------------------------------------------------------------
# Projection ("what should be in this account on day X") — pure function
# ---------------------------------------------------------------------------


def project_balance(
    store_user: str, workspace: str, book: dict, account_id: str, target_date: str
) -> dict:
    book = finance_service.fresh_book(store_user, workspace, book)
    try:
        target = date.fromisoformat(target_date)
    except (TypeError, ValueError):
        raise ValueError("date must be YYYY-MM-DD")
    if not any(a["id"] == account_id for a in book.get("accounts", [])):
        raise ValueError("Unknown account")
    today = date.today()

    balances = finance_service.account_balances(store_user, workspace, book)
    current = balances.get(account_id, 0)

    future_items: list[dict] = []
    for item in list_recurring(store_user, workspace, book["id"]):
        if not item.get("active", True) or item.get("account_id") != account_id:
            continue
        try:
            due = date.fromisoformat(item["next_due"])
        except (TypeError, ValueError):
            continue
        cadence = item.get("cadence", "monthly")
        count = 0
        while due <= target and count < _MAX_PROJECTION_ITEMS:
            if due > today:
                future_items.append(
                    {
                        "date": due.isoformat(),
                        "name": item["name"],
                        "amount_cents": item["amount_cents"],
                        "source": "recurring",
                    }
                )
            due = date.fromisoformat(advance_due(due.isoformat(), cadence))
            count += 1

    for item in list_planned(store_user, workspace, book["id"]):
        if item.get("done") or item.get("account_id") != account_id:
            continue
        try:
            item_date = date.fromisoformat(item["date"])
        except (TypeError, ValueError):
            continue
        if today < item_date <= target:
            future_items.append(
                {
                    "date": item["date"],
                    "name": item["name"],
                    "amount_cents": item["amount_cents"],
                    "source": "planned",
                }
            )

    future_items.sort(key=lambda i: i["date"])
    projected = current + sum(i["amount_cents"] for i in future_items)
    return {
        "account_id": account_id,
        "target_date": target.isoformat(),
        "current_cents": current,
        "projected_cents": projected,
        "items": future_items,
    }


# ---------------------------------------------------------------------------
# Deviation alerts (bank-reported vs ledger balance = fraud early-warning)
# ---------------------------------------------------------------------------


def check_deviation(store_user: str, workspace: str, book: dict) -> None:
    """Compare each account's bank-reported balance against the ledger balance.
    Alert when the drift exceeds the account's threshold. Deduped per day,
    re-alerting only when the delta changes by >10%."""
    balances = finance_service.account_balances(store_user, workspace, book)
    today = date.today().isoformat()
    for account in book.get("accounts", []):
        threshold = account.get("deviation_threshold_cents")
        real = account.get("synced_balance_cents")
        if not threshold or real is None or account.get("archived"):
            continue
        expected = balances.get(account["id"], 0)
        delta = real - expected
        if abs(delta) <= threshold:
            continue
        last = account.get("last_deviation_alert") or {}
        if last.get("date") == today:
            prev_delta = last.get("delta_cents", 0)
            if prev_delta and abs(delta - prev_delta) <= abs(prev_delta) * 0.1:
                continue
        finance_service.set_deviation_alert_state(
            store_user, workspace, book["id"], account["id"], {"date": today, "delta_cents": delta}
        )
        direction = "more" if delta > 0 else "less"
        _notify(
            _alert_recipients(store_user),
            f"⚠️ Balance deviation on {account['name']}",
            f"{book['name']}: the bank reports {_fmt(real)} but the ledger expects "
            f"{_fmt(expected)} — {_fmt(abs(delta))} {direction} than expected. "
            "Check for unrecorded or unauthorized activity.",
            book["id"],
        )


# ---------------------------------------------------------------------------
# Hooks + nightly job
# ---------------------------------------------------------------------------


def on_transactions_added(store_user: str, workspace: str, book_id: str, txs: list[dict]) -> None:
    """Post-write hook (manual add, sync, CSV): bill matching + budget alerts.
    Never raises — planning must not break the write path."""
    try:
        book = finance_service.get_book(store_user, workspace, book_id)
        if not book:
            return
        for tx in txs:
            match_bill(store_user, workspace, book, tx)
        months = {t["date"][:7] for t in txs}
        for month in months:
            check_budget_alerts(store_user, workspace, book, month)
    except Exception:
        logger.exception("finance planning hook failed")


def run_nightly() -> None:
    """Missed bills + budget alerts + deviation checks across every store."""
    from services import auth_service

    stores: list[tuple[str, str]] = [
        (finance_service.POOL_HOUSEHOLD, "personal"),
        (finance_service.POOL_TEAM, "business"),
    ]
    for user in auth_service.list_users():
        for ws in user.get("workspaces", ["personal"]):
            stores.append((user["name"], ws))

    month = date.today().isoformat()[:7]
    for store_user, ws in stores:
        try:
            for book in finance_service.list_books(store_user, ws):
                if book.get("archived"):
                    continue
                check_missed_bills(store_user, ws, book)
                check_budget_alerts(store_user, ws, book, month)
                check_deviation(store_user, ws, book)
        except Exception:
            logger.exception("finance nightly failed for %s/%s", store_user, ws)
