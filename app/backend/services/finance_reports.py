"""Finance reports — all values computed on read from transaction shards.

Phase A ships the monthly report and net worth; P&L, trends and the tax
summary build on the same helpers in the invoicing phase.
"""

import calendar
import re

from services import finance_service


def month_end(year: int, month: int) -> str:
    """Last day of a month as ISO date — never fabricate day 31."""
    return f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def _month_transactions(store_user: str, workspace: str, book: dict, month: str) -> list[dict]:
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        raise ValueError(f"Invalid month: {month!r} (expected YYYY-MM)")
    year, month_num = int(month[:4]), int(month[5:7])
    items, _total = finance_service.list_transactions(
        store_user,
        workspace,
        book["id"],
        date_from=f"{month}-01",
        date_to=month_end(year, month_num),
        limit=100000,
    )
    return items


def monthly_report(store_user: str, workspace: str, book: dict, month: str) -> dict:
    """Income vs expenses + per-category breakdown for one calendar month."""
    transactions = _month_transactions(store_user, workspace, book, month)

    income = sum(t["amount_cents"] for t in transactions if t["amount_cents"] > 0)
    expenses = sum(t["amount_cents"] for t in transactions if t["amount_cents"] < 0)

    by_category: dict[str, dict] = {}
    for t in transactions:
        name = t.get("category") or ""
        bucket = by_category.setdefault(
            name, {"category": name, "income_cents": 0, "expense_cents": 0, "count": 0}
        )
        if t["amount_cents"] > 0:
            bucket["income_cents"] += t["amount_cents"]
        else:
            bucket["expense_cents"] += t["amount_cents"]
        bucket["count"] += 1

    categories = sorted(
        by_category.values(),
        key=lambda c: (c["expense_cents"], -c["income_cents"]),
    )
    return {
        "month": month,
        "income_cents": income,
        "expense_cents": expenses,
        "net_cents": income + expenses,
        "transaction_count": len(transactions),
        "categories": categories,
    }


def _range_transactions(
    store_user: str, workspace: str, book: dict, date_from: str, date_to: str
) -> list[dict]:
    items, _total = finance_service.list_transactions(
        store_user, workspace, book["id"], date_from=date_from, date_to=date_to, limit=1000000
    )
    return items


def pnl(
    store_user: str,
    workspace: str,
    book: dict,
    year: int,
    period: str = "year",
    quarter: int | None = None,
    month: int | None = None,
) -> dict:
    """Income statement for a year / quarter / month — computed on read."""
    if period == "month":
        if not month or not 1 <= month <= 12:
            raise ValueError("month must be 1-12")
        date_from, date_to = f"{year}-{month:02d}-01", month_end(year, month)
        label = f"{year}-{month:02d}"
    elif period == "quarter":
        if not quarter or not 1 <= quarter <= 4:
            raise ValueError("quarter must be 1-4")
        start_month = (quarter - 1) * 3 + 1
        date_from = f"{year}-{start_month:02d}-01"
        date_to = month_end(year, start_month + 2)
        label = f"Q{quarter} {year}"
    else:
        date_from, date_to = f"{year}-01-01", f"{year}-12-31"
        label = str(year)

    transactions = _range_transactions(store_user, workspace, book, date_from, date_to)
    income_by_cat: dict[str, int] = {}
    expense_by_cat: dict[str, int] = {}
    for t in transactions:
        name = t.get("category") or ""
        if t["amount_cents"] > 0:
            income_by_cat[name] = income_by_cat.get(name, 0) + t["amount_cents"]
        else:
            expense_by_cat[name] = expense_by_cat.get(name, 0) + t["amount_cents"]
    income = sum(income_by_cat.values())
    expenses = sum(expense_by_cat.values())
    return {
        "period": label,
        "from": date_from,
        "to": date_to,
        "income_cents": income,
        "expense_cents": expenses,
        "net_cents": income + expenses,
        "income_by_category": sorted(
            [{"category": k, "amount_cents": v} for k, v in income_by_cat.items()],
            key=lambda e: -e["amount_cents"],
        ),
        "expense_by_category": sorted(
            [{"category": k, "amount_cents": v} for k, v in expense_by_cat.items()],
            key=lambda e: e["amount_cents"],
        ),
        "transaction_count": len(transactions),
    }


def tax_summary(store_user: str, workspace: str, book: dict, year: int) -> dict:
    """Deductible transactions grouped by tax category — the year-end handoff."""
    transactions = _range_transactions(
        store_user, workspace, book, f"{year}-01-01", f"{year}-12-31"
    )
    deductible = [t for t in transactions if t.get("deductible")]
    by_bucket: dict[str, dict] = {}
    for t in deductible:
        bucket = t.get("tax_category") or "(unassigned)"
        entry = by_bucket.setdefault(
            bucket, {"tax_category": bucket, "amount_cents": 0, "count": 0}
        )
        entry["amount_cents"] += t["amount_cents"]
        entry["count"] += 1
    return {
        "year": year,
        "total_cents": sum(t["amount_cents"] for t in deductible),
        "count": len(deductible),
        "buckets": sorted(by_bucket.values(), key=lambda e: e["amount_cents"]),
    }


def tax_summary_csv(store_user: str, workspace: str, book: dict, year: int) -> str:
    """Line-level CSV of deductible transactions for the accountant."""
    transactions = _range_transactions(
        store_user, workspace, book, f"{year}-01-01", f"{year}-12-31"
    )
    lines = ["date,payee,category,tax_category,amount"]
    for t in sorted((t for t in transactions if t.get("deductible")), key=lambda t: t["date"]):
        payee = (t.get("payee") or "").replace('"', "'")
        lines.append(
            f'{t["date"]},"{payee}","{t.get("category") or ""}",'
            f'"{t.get("tax_category") or ""}",{t["amount_cents"] / 100:.2f}'
        )
    return "\n".join(lines) + "\n"


def net_worth(viewer: str, viewer_role: str, is_admin: bool, workspace: str) -> dict:
    """Total across all visible books' active accounts (caps-aware in the
    sharing phase — books whose access level hides balances get skipped)."""
    books = finance_service.list_visible_books(viewer, viewer_role, is_admin, workspace)
    entries = []
    total = 0
    for book in books:
        # Contribute access without the see_balances cap never leaks totals
        if book.get("_access") == "contribute" and not (book.get("_caps") or {}).get(
            "see_balances"
        ):
            continue
        store_user = finance_service.store_for_annotated(book, viewer, workspace)
        summary = finance_service.book_summary(store_user, workspace, book)
        entries.append(
            {
                "book_id": book["id"],
                "name": book["name"],
                "icon": book.get("icon", "💰"),
                "currency": book.get("currency", "USD"),
                "total_cents": summary["total_cents"],
                "_owner": book.get("_owner"),
            }
        )
        total += summary["total_cents"]
    return {"total_cents": total, "books": entries}
