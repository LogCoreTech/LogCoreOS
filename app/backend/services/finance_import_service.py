"""CSV bank-statement import — the zero-third-party fallback to SimpleFIN.

Two-step flow: preview (detect columns, show sample rows) then commit with an
explicit column mapping. Dedup via import_hash = sha1(date|amount_cents|payee)
so re-importing the same statement is a no-op.
"""

import csv
import hashlib
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from services import finance_service

MAX_CSV_BYTES = 5 * 1024 * 1024
_PREVIEW_ROWS = 5
_MAX_ROWS = 10000

DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"]


def _decode(content: bytes) -> str:
    if len(content) > MAX_CSV_BYTES:
        raise ValueError("CSV too large (max 5 MB)")
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode file as text")


def _reader(text: str) -> csv.reader:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return csv.reader(io.StringIO(text), dialect)


def preview_csv(content: bytes) -> dict:
    """Headers + sample rows so the user can map columns before committing."""
    rows = list(_reader(_decode(content)))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if len(rows) < 2:
        raise ValueError("CSV needs a header row and at least one data row")
    return {
        "headers": [h.strip() for h in rows[0]],
        "rows": rows[1 : 1 + _PREVIEW_ROWS],
        "total_rows": len(rows) - 1,
    }


def parse_date(value: str, date_format: str | None = None) -> str:
    value = (value or "").strip()
    formats = [date_format] if date_format else DATE_FORMATS
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except (ValueError, TypeError):
            continue
    raise ValueError(f"Unparseable date: {value!r}")


def parse_amount(value: str) -> int:
    """Decimal string → signed integer cents. Handles $, commas, (parens)=negative."""
    cleaned = (value or "").strip().replace("$", "").replace(",", "")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    try:
        cents = int((Decimal(cleaned) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        raise ValueError(f"Unparseable amount: {value!r}")
    return -cents if negative else cents


def commit_csv(
    store_user: str,
    workspace: str,
    book: dict,
    content: bytes,
    mapping: dict,
    created_by: str,
) -> dict:
    """Import rows using the column mapping. Returns {created, skipped, errors}.

    mapping: {date_col, amount_col, payee_col?, notes_col?, date_format?,
              invert_amounts?, account_id}
    """
    rows = list(_reader(_decode(content)))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if len(rows) < 2:
        raise ValueError("CSV needs a header row and at least one data row")
    if len(rows) - 1 > _MAX_ROWS:
        raise ValueError(f"Too many rows (max {_MAX_ROWS})")
    headers = [h.strip() for h in rows[0]]

    def col_index(key: str, required: bool = True) -> int | None:
        name = mapping.get(key)
        if name in (None, ""):
            if required:
                raise ValueError(f"Missing column mapping: {key}")
            return None
        if name not in headers:
            raise ValueError(f"Column {name!r} not in CSV headers")
        return headers.index(name)

    date_idx = col_index("date_col")
    amount_idx = col_index("amount_col")
    payee_idx = col_index("payee_col", required=False)
    notes_idx = col_index("notes_col", required=False)
    invert = bool(mapping.get("invert_amounts"))
    date_format = mapping.get("date_format") or None
    account_id = mapping.get("account_id") or ""

    _sf_ids, seen_hashes = finance_service.existing_dedup_keys(store_user, workspace, book["id"])
    new_txs = []
    skipped = 0
    errors: list[str] = []
    for line_no, row in enumerate(rows[1:], start=2):
        try:
            tx_date = parse_date(row[date_idx], date_format)
            cents = parse_amount(row[amount_idx])
            if invert:
                cents = -cents
            if cents == 0:
                skipped += 1
                continue
            payee = row[payee_idx].strip() if payee_idx is not None and payee_idx < len(row) else ""
            notes = row[notes_idx].strip() if notes_idx is not None and notes_idx < len(row) else ""
        except (ValueError, IndexError) as exc:
            errors.append(f"Row {line_no}: {exc}")
            if len(errors) >= 20:
                errors.append("… more errors truncated")
                break
            continue
        import_hash = hashlib.sha1(f"{tx_date}|{cents}|{payee.lower()}".encode()).hexdigest()
        if import_hash in seen_hashes:
            skipped += 1
            continue
        seen_hashes.add(import_hash)
        new_txs.append(
            {
                "date": tx_date,
                "amount_cents": cents,
                "account_id": account_id,
                "category": finance_service.apply_rules(store_user, workspace, book, payee),
                "payee": payee,
                "notes": notes,
                "import_hash": import_hash,
            }
        )

    if new_txs:
        created_records = finance_service.bulk_add_transactions(
            store_user, workspace, book["id"], new_txs, created_by=created_by, source="csv"
        )
        from services import finance_planning_service

        finance_planning_service.on_transactions_added(
            store_user, workspace, book["id"], created_records
        )
    result = {"created": len(new_txs), "skipped": skipped}
    if errors:
        result["errors"] = errors
    return result
