"""Trash registry contract for the finance module — see module_registry.py's
trash_dispatch()/owned_trash_types and services/trash_service.py's module
docstring for the shared per-module contract. Finance owns the most record
types of any module (10, across 3 core services) — this single file
dispatches describe()/restore() by record_type rather than splitting into
per-service handler files, since trash_dispatch() only ever looks up by
record_type, never by which service originally owned the function.

`original_location` carries whatever parent ids a given record_type needs
to restore into the right place (a book_id, a book_id+year, a
book_id+tx_id, or a book_id+invoice_id) — trash_service.py itself never
interprets this, it's opaque to everything except this file's own restore().
"""

from services import finance_invoice_service as invoicing
from services import finance_planning_service as planning
from services import finance_service
from services.file_service import ws_path


def _fmt_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


RECORD_TYPES = [
    "book",
    "account",
    "transaction",
    "receipt",
    "rule",
    "recurring",
    "planned",
    "client",
    "invoice",
    "payment",
]


def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    p = payload or {}
    if record_type == "book":
        return p.get("name") or "Untitled book", "Finance"
    if record_type == "account":
        return p.get("name") or "Untitled account", "Finance · Account"
    if record_type == "transaction":
        title = p.get("payee") or "Transaction"
        return title, f"Finance · {_fmt_cents(p.get('amount_cents', 0))}"
    if record_type == "receipt":
        return p.get("filename") or "Receipt", "Finance · Receipt"
    if record_type == "rule":
        return p.get("payee_norm") or "Rule", f"Finance · → {p.get('category') or 'Uncategorized'}"
    if record_type == "recurring":
        return (
            p.get("name") or "Recurring bill",
            f"Finance · {_fmt_cents(p.get('amount_cents', 0))}",
        )
    if record_type == "planned":
        return p.get("name") or "Planned item", f"Finance · {_fmt_cents(p.get('amount_cents', 0))}"
    if record_type == "client":
        return p.get("name") or "Untitled client", "Finance · Client"
    if record_type == "invoice":
        return p.get("number") or "Invoice", "Finance · Invoice"
    if record_type == "payment":
        return f"Payment · {_fmt_cents(p.get('amount_cents', 0))}", "Finance"
    return "Finance record", "Finance"


def _restore_book(store_user: str, workspace: str, entry: dict) -> dict:
    book = entry["payload"]
    if finance_service.get_book(store_user, workspace, book["id"]) is not None:
        raise ValueError("A book with this ID already exists — it may have already been restored.")

    file_ref = entry.get("file_ref")
    if file_ref:
        from services.file_service import finance_book_dir

        src = ws_path(store_user, workspace) / file_ref
        ws = finance_service.store_workspace(store_user, workspace)
        dest = finance_book_dir(store_user, book["id"], ws)
        if src.exists() and not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)

    data = finance_service._load(store_user, workspace)
    data.setdefault("books", []).append(book)
    finance_service._save(store_user, workspace, data)
    return book


def _restore_account(store_user: str, workspace: str, entry: dict) -> dict:
    account = entry["payload"]
    book_id = entry["original_location"]["book_id"]
    data = finance_service._load(store_user, workspace)
    for i, book in enumerate(data.get("books", [])):
        if book["id"] != book_id:
            continue
        if any(a["id"] == account["id"] for a in book.get("accounts", [])):
            raise ValueError(
                "An account with this ID already exists — it may have already been restored."
            )
        book.setdefault("accounts", []).append(account)
        data["books"][i] = book
        finance_service._save(store_user, workspace, data)
        return account
    raise ValueError("The book this account belonged to no longer exists.")


def _restore_transaction(store_user: str, workspace: str, entry: dict) -> dict:
    tx = entry["payload"]
    loc = entry["original_location"]
    book_id, year = loc["book_id"], loc["year"]
    if finance_service.get_transaction(store_user, workspace, book_id, tx["id"]) is not None:
        raise ValueError(
            "A transaction with this ID already exists — it may have already been restored."
        )

    file_ref = entry.get("file_ref")
    if file_ref:
        src = ws_path(store_user, workspace) / file_ref
        dest = finance_service._receipts_dir(store_user, workspace, book_id, tx["id"])
        if src.exists() and not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)

    shard = finance_service._read_shard(store_user, workspace, book_id, year)
    shard.setdefault("transactions", []).append(tx)
    finance_service._write_shard(store_user, workspace, book_id, year, shard)
    return tx


def _restore_receipt(store_user: str, workspace: str, entry: dict) -> dict:
    meta = entry["payload"]
    loc = entry["original_location"]
    book_id, tx_id = loc["book_id"], loc["tx_id"]
    tx = finance_service.get_transaction(store_user, workspace, book_id, tx_id)
    if tx is None:
        raise ValueError("The transaction this receipt belonged to no longer exists.")
    attachments = list(tx.get("attachments") or [])
    if any(a["id"] == meta["id"] for a in attachments):
        raise ValueError(
            "A receipt with this ID already exists — it may have already been restored."
        )

    file_ref = entry.get("file_ref")
    if file_ref:
        ext = finance_service.RECEIPT_TYPES.get(meta["mime"], "bin")
        src = ws_path(store_user, workspace) / file_ref
        dest = finance_service._receipts_dir(store_user, workspace, book_id, tx_id) / (
            f"{meta['id']}.{ext}"
        )
        if src.exists() and not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)

    attachments.append(meta)
    finance_service._update_tx_attachments(store_user, workspace, book_id, tx_id, attachments)
    return meta


def _restore_rule(store_user: str, workspace: str, entry: dict) -> dict:
    from services.file_service import read_json, write_json

    rule = entry["payload"]
    book_id = entry["original_location"]["book_id"]
    path = finance_service._rules_file(store_user, workspace, book_id)
    data = read_json(path, default={"rules": []})
    if any(r.get("id") == rule.get("id") for r in data.get("rules", [])):
        raise ValueError("A rule with this ID already exists — it may have already been restored.")
    data.setdefault("rules", []).append(rule)
    write_json(path, data)
    return rule


def _restore_recurring(store_user: str, workspace: str, entry: dict) -> dict:
    item = entry["payload"]
    book_id = entry["original_location"]["book_id"]
    items = planning.list_recurring(store_user, workspace, book_id)
    if any(i["id"] == item["id"] for i in items):
        raise ValueError(
            "A recurring item with this ID already exists — it may have already been restored."
        )
    items.append(item)
    planning._save_recurring(store_user, workspace, book_id, items)
    return item


def _restore_planned(store_user: str, workspace: str, entry: dict) -> dict:
    item = entry["payload"]
    book_id = entry["original_location"]["book_id"]
    items = planning.list_planned(store_user, workspace, book_id)
    if any(i["id"] == item["id"] for i in items):
        raise ValueError(
            "A planned item with this ID already exists — it may have already been restored."
        )
    items.append(item)
    planning._save_planned(store_user, workspace, book_id, items)
    return item


def _restore_client(store_user: str, workspace: str, entry: dict) -> dict:
    client = entry["payload"]
    book_id = entry["original_location"]["book_id"]
    clients = invoicing.list_clients(store_user, workspace, book_id)
    if any(c["id"] == client["id"] for c in clients):
        raise ValueError(
            "A client with this ID already exists — it may have already been restored."
        )
    clients.append(client)
    invoicing._save_clients(store_user, workspace, book_id, clients)
    return client


def _restore_invoice(store_user: str, workspace: str, entry: dict) -> dict:
    invoice = entry["payload"]
    book_id = entry["original_location"]["book_id"]
    invoices = invoicing._raw_invoices(store_user, workspace, book_id)
    if any(i["id"] == invoice["id"] for i in invoices):
        raise ValueError(
            "An invoice with this ID already exists — it may have already been restored."
        )
    invoices.append(invoice)
    invoicing._save_invoices(store_user, workspace, book_id, invoices)
    return invoicing.annotate_invoice(invoice)


def _restore_payment(store_user: str, workspace: str, entry: dict) -> dict:
    payment = entry["payload"]
    loc = entry["original_location"]
    book_id, invoice_id = loc["book_id"], loc["invoice_id"]
    invoices = invoicing._raw_invoices(store_user, workspace, book_id)
    for i, invoice in enumerate(invoices):
        if invoice["id"] != invoice_id:
            continue
        payments = invoice.get("payments", [])
        if any(p["id"] == payment["id"] for p in payments):
            raise ValueError(
                "A payment with this ID already exists — it may have already been restored."
            )
        invoice.setdefault("payments", []).append(payment)
        annotated = invoicing.annotate_invoice(invoice)
        if annotated["balance_cents"] <= 0 and invoice.get("status") in ("draft", "sent"):
            invoice["status"] = "paid"
        invoices[i] = invoice
        invoicing._save_invoices(store_user, workspace, book_id, invoices)
        return invoicing.annotate_invoice(invoice)
    raise ValueError("The invoice this payment belonged to no longer exists.")


_RESTORERS = {
    "book": _restore_book,
    "account": _restore_account,
    "transaction": _restore_transaction,
    "receipt": _restore_receipt,
    "rule": _restore_rule,
    "recurring": _restore_recurring,
    "planned": _restore_planned,
    "client": _restore_client,
    "invoice": _restore_invoice,
    "payment": _restore_payment,
}


def restore(store_user: str, workspace: str, entry: dict) -> dict:
    restorer = _RESTORERS.get(entry["record_type"])
    if restorer is None:
        raise ValueError(f"Unknown finance trash record type: {entry['record_type']!r}")
    return restorer(store_user, workspace, entry)


def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """list_trash_for_user() only ever reads from the caller's own store or
    an enabled (admin-only) pool's store — Finance's own access model has no
    finer per-item permission beyond that on either surface today, so every
    entry that reaches this point is already something `user` is entitled
    to see."""
    return True
