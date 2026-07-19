"""Finance invoicing: clients, invoices, payments, accounts receivable.

Answers the owner's core question per client: did they pay, how much, when,
and who is behind. All totals (invoice total, paid, balance, overdue, AR
rollups) are computed on read — `status` stores only the user-set lifecycle
(draft|sent|paid|void); "overdue" is always derived, and a fully paid invoice
flips to "paid" automatically when a payment lands.

Clients carry a reserved `contact_id` for the FUTURE separate CRM module —
this module never populates it.
"""

import uuid
from datetime import date, datetime, timezone

from services import finance_service
from services.file_service import finance_book_dir, read_json, write_json

MAX_LINE_ITEMS = 50
MAX_CLIENTS = 1000
MAX_INVOICES = 5000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _book_file(store_user: str, workspace: str, book_id: str, name: str):
    ws = finance_service.store_workspace(store_user, workspace)
    return finance_book_dir(store_user, book_id, ws) / name


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


def list_clients(store_user: str, workspace: str, book_id: str) -> list[dict]:
    return read_json(
        _book_file(store_user, workspace, book_id, "clients.json"), default={"clients": []}
    ).get("clients", [])


def _save_clients(store_user: str, workspace: str, book_id: str, clients: list[dict]) -> None:
    write_json(_book_file(store_user, workspace, book_id, "clients.json"), {"clients": clients})


def _validate_client(data: dict, partial: bool = False) -> dict:
    out: dict = {}
    if "name" in data or not partial:
        name = (data.get("name") or "").strip()
        if not name or len(name) > 120:
            raise ValueError("Client name must be 1-120 characters")
        out["name"] = name
    for key, cap in (("email", 200), ("phone", 40), ("notes", 2000)):
        if key in data:
            out[key] = (data.get(key) or "").strip()[:cap]
    if "contact_id" in data:
        out["contact_id"] = (data.get("contact_id") or None) or None  # CRM contact link
    if "archived" in data:
        out["archived"] = bool(data["archived"])
    return out


def add_client(store_user: str, workspace: str, book_id: str, data: dict, created_by: str) -> dict:
    clients = list_clients(store_user, workspace, book_id)
    if len(clients) >= MAX_CLIENTS:
        raise ValueError("Client limit reached")
    fields = _validate_client(data)
    client = {
        "id": str(uuid.uuid4()),
        "email": "",
        "phone": "",
        "notes": "",
        "contact_id": None,  # reserved for the future CRM module
        "archived": False,
        "created_by": created_by,
        "created_at": _now(),
        **fields,
    }
    clients.append(client)
    _save_clients(store_user, workspace, book_id, clients)
    return client


def update_client(
    store_user: str, workspace: str, book_id: str, client_id: str, updates: dict
) -> dict | None:
    clients = list_clients(store_user, workspace, book_id)
    for i, client in enumerate(clients):
        if client["id"] != client_id:
            continue
        clients[i] = {**client, **_validate_client(updates, partial=True)}
        _save_clients(store_user, workspace, book_id, clients)
        return clients[i]
    return None


def delete_client(store_user: str, workspace: str, book_id: str, client_id: str) -> bool:
    """Callers must first check client_has_invoices() — archive instead."""
    clients = list_clients(store_user, workspace, book_id)
    remaining = [c for c in clients if c["id"] != client_id]
    if len(remaining) == len(clients):
        return False
    _save_clients(store_user, workspace, book_id, remaining)
    return True


def client_has_invoices(store_user: str, workspace: str, book_id: str, client_id: str) -> bool:
    return any(
        inv.get("client_id") == client_id for inv in _raw_invoices(store_user, workspace, book_id)
    )


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


def _raw_invoices(store_user: str, workspace: str, book_id: str) -> list[dict]:
    return read_json(
        _book_file(store_user, workspace, book_id, "invoices.json"), default={"invoices": []}
    ).get("invoices", [])


def _save_invoices(store_user: str, workspace: str, book_id: str, invoices: list[dict]) -> None:
    write_json(_book_file(store_user, workspace, book_id, "invoices.json"), {"invoices": invoices})


def _validate_line_items(items: list) -> list[dict]:
    if not isinstance(items, list) or not items:
        raise ValueError("Invoice needs at least one line item")
    if len(items) > MAX_LINE_ITEMS:
        raise ValueError(f"Max {MAX_LINE_ITEMS} line items")
    cleaned = []
    for item in items:
        description = (item.get("description") or "").strip()
        if not description or len(description) > 200:
            raise ValueError("Line item description must be 1-200 characters")
        qty = item.get("qty", 1)
        if isinstance(qty, bool) or not isinstance(qty, (int, float)) or qty <= 0 or qty > 100000:
            raise ValueError("Line item qty must be a positive number")
        unit = item.get("unit_cents")
        if isinstance(unit, bool) or not isinstance(unit, int):
            raise ValueError("unit_cents must be an integer (cents)")
        cleaned.append({"description": description, "qty": qty, "unit_cents": unit})
    return cleaned


def _parse_date(value, label: str) -> str:
    try:
        return date.fromisoformat(value or "").isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be YYYY-MM-DD")


def annotate_invoice(invoice: dict) -> dict:
    """Attach computed totals — never stored."""
    subtotal = round(sum(i["qty"] * i["unit_cents"] for i in invoice.get("line_items", [])))
    tax_pct = invoice.get("tax_pct") or 0
    total = round(subtotal * (1 + tax_pct / 100))
    paid = sum(p["amount_cents"] for p in invoice.get("payments", []))
    balance = total - paid
    overdue = (
        invoice.get("status") == "sent"
        and balance > 0
        and (invoice.get("due_date") or "9999") < date.today().isoformat()
    )
    return {
        **invoice,
        "subtotal_cents": subtotal,
        "total_cents": total,
        "paid_cents": paid,
        "balance_cents": balance,
        "overdue": overdue,
    }


def list_invoices(store_user: str, workspace: str, book_id: str) -> list[dict]:
    invoices = [annotate_invoice(i) for i in _raw_invoices(store_user, workspace, book_id)]
    invoices.sort(key=lambda i: (i.get("issue_date") or "", i.get("number") or ""), reverse=True)
    return invoices


def get_invoice(store_user: str, workspace: str, book_id: str, invoice_id: str) -> dict | None:
    inv = next(
        (i for i in _raw_invoices(store_user, workspace, book_id) if i["id"] == invoice_id), None
    )
    return annotate_invoice(inv) if inv else None


def list_invoices_for_deal(
    viewer: str, viewer_role: str, is_admin: bool, workspace: str, deal_id: str
) -> list[dict]:
    """Invoices billing this deal across every book the viewer can see, newest
    first. Contribute-capped books without see_balances are skipped — the same
    rule _require_full_read applies to per-book invoice reads."""
    results: list[dict] = []
    for book in finance_service.list_visible_books(viewer, viewer_role, is_admin, workspace):
        if book.get("_access") == "contribute" and not (book.get("_caps") or {}).get(
            "see_balances"
        ):
            continue
        store_user = finance_service.store_for_annotated(book, viewer, workspace)
        for inv in _raw_invoices(store_user, workspace, book["id"]):
            if inv.get("deal_id") == deal_id:
                results.append(
                    {**annotate_invoice(inv), "book_id": book["id"], "book_name": book["name"]}
                )
    results.sort(key=lambda i: (i.get("issue_date") or "", i.get("number") or ""), reverse=True)
    return results


def create_invoice(
    store_user: str, workspace: str, book_id: str, data: dict, created_by: str
) -> dict:
    invoices = _raw_invoices(store_user, workspace, book_id)
    if len(invoices) >= MAX_INVOICES:
        raise ValueError("Invoice limit reached")
    client_id = data.get("client_id")
    if client_id and not any(
        c["id"] == client_id for c in list_clients(store_user, workspace, book_id)
    ):
        raise ValueError("Unknown client")
    tax_pct = data.get("tax_pct", 0)
    if isinstance(tax_pct, bool) or not isinstance(tax_pct, (int, float)) or not 0 <= tax_pct <= 50:
        raise ValueError("tax_pct must be between 0 and 50")
    invoice = {
        "id": str(uuid.uuid4()),
        "number": finance_service.next_invoice_number(store_user, workspace, book_id),
        "client_id": client_id,
        "deal_id": (str(data.get("deal_id") or "")[:64] or None),  # CRM deal this invoice bills
        "status": "draft",
        "issue_date": _parse_date(data.get("issue_date") or date.today().isoformat(), "issue_date"),
        "due_date": _parse_date(data.get("due_date"), "due_date"),
        "line_items": _validate_line_items(data.get("line_items")),
        "tax_pct": tax_pct,
        "notes": (data.get("notes") or "").strip()[:2000],
        "payments": [],
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
    }
    invoices.append(invoice)
    _save_invoices(store_user, workspace, book_id, invoices)
    return annotate_invoice(invoice)


def update_invoice(
    store_user: str, workspace: str, book_id: str, invoice_id: str, updates: dict
) -> dict | None:
    invoices = _raw_invoices(store_user, workspace, book_id)
    for i, invoice in enumerate(invoices):
        if invoice["id"] != invoice_id:
            continue
        allowed: dict = {}
        if "client_id" in updates:
            client_id = updates["client_id"]
            if client_id and not any(
                c["id"] == client_id for c in list_clients(store_user, workspace, book_id)
            ):
                raise ValueError("Unknown client")
            allowed["client_id"] = client_id
        if "status" in updates:
            if updates["status"] not in ("draft", "sent", "paid", "void"):
                raise ValueError("Invalid status")
            allowed["status"] = updates["status"]
        if "issue_date" in updates:
            allowed["issue_date"] = _parse_date(updates["issue_date"], "issue_date")
        if "due_date" in updates:
            allowed["due_date"] = _parse_date(updates["due_date"], "due_date")
        if "line_items" in updates:
            allowed["line_items"] = _validate_line_items(updates["line_items"])
        if "tax_pct" in updates:
            tax_pct = updates["tax_pct"]
            if (
                isinstance(tax_pct, bool)
                or not isinstance(tax_pct, (int, float))
                or not 0 <= tax_pct <= 50
            ):
                raise ValueError("tax_pct must be between 0 and 50")
            allowed["tax_pct"] = tax_pct
        if "notes" in updates:
            allowed["notes"] = (updates["notes"] or "").strip()[:2000]
        allowed["updated_at"] = _now()
        invoices[i] = {**invoice, **allowed}
        _save_invoices(store_user, workspace, book_id, invoices)
        return annotate_invoice(invoices[i])
    return None


def delete_invoice(store_user: str, workspace: str, book_id: str, invoice_id: str) -> bool:
    invoices = _raw_invoices(store_user, workspace, book_id)
    remaining = [i for i in invoices if i["id"] != invoice_id]
    if len(remaining) == len(invoices):
        return False
    _save_invoices(store_user, workspace, book_id, remaining)
    return True


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


def record_payment(
    store_user: str,
    workspace: str,
    book_id: str,
    invoice_id: str,
    data: dict,
    created_by: str,
) -> dict | None:
    """Append a (possibly partial) payment. Optionally creates a linked income
    transaction in the given account. Auto-flips status to 'paid' at zero balance."""
    amount = data.get("amount_cents")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError("amount_cents must be a positive integer")
    pay_date = _parse_date(data.get("date") or date.today().isoformat(), "date")

    invoices = _raw_invoices(store_user, workspace, book_id)
    for i, invoice in enumerate(invoices):
        if invoice["id"] != invoice_id:
            continue
        payment = {
            "id": str(uuid.uuid4()),
            "date": pay_date,
            "amount_cents": amount,
            "method": (data.get("method") or "").strip()[:40],
            "tx_id": None,
            "recorded_by": created_by,
        }
        if data.get("account_id"):
            client = next(
                (
                    c
                    for c in list_clients(store_user, workspace, book_id)
                    if c["id"] == invoice.get("client_id")
                ),
                None,
            )
            tx = finance_service.add_transaction(
                store_user,
                workspace,
                book_id,
                {
                    "date": pay_date,
                    "amount_cents": amount,
                    "account_id": data["account_id"],
                    "category": data.get("category", ""),
                    "payee": client["name"] if client else "Invoice payment",
                    "notes": f"Payment on {invoice.get('number')}",
                    "invoice_id": invoice_id,
                    "client_id": invoice.get("client_id"),
                    "deal_id": invoice.get("deal_id"),
                    "asset_id": _deal_single_asset(created_by, workspace, invoice.get("deal_id")),
                },
                created_by=created_by,
                source="manual",
            )
            payment["tx_id"] = tx["id"]
        invoice.setdefault("payments", []).append(payment)
        annotated = annotate_invoice(invoice)
        if annotated["balance_cents"] <= 0 and invoice.get("status") in ("draft", "sent"):
            invoice["status"] = "paid"
        invoice["updated_at"] = _now()
        invoices[i] = invoice
        _save_invoices(store_user, workspace, book_id, invoices)
        return annotate_invoice(invoice)
    return None


def _deal_single_asset(viewer: str, workspace: str, deal_id: str | None) -> str | None:
    """Best-effort: when the invoice's deal has exactly one linked asset, the
    payment's transaction auto-links it. Never raises — Finance must work
    without Contacts (same guard pattern as _suggest_payee_contact)."""
    if not deal_id:
        return None
    try:
        from services import contacts_service

        found = contacts_service.find_deal(viewer, "member", False, workspace, deal_id)
        if not found:
            return None
        _store, deal, _contact, _access = found
        ids = deal.get("linked_asset_ids") or []
        return ids[0] if len(ids) == 1 else None
    except Exception:
        return None


def delete_payment(
    store_user: str, workspace: str, book_id: str, invoice_id: str, payment_id: str
) -> dict | None:
    """Remove a payment record. The linked transaction (if any) stays — delete
    it from the ledger separately if it was a mistake."""
    invoices = _raw_invoices(store_user, workspace, book_id)
    for i, invoice in enumerate(invoices):
        if invoice["id"] != invoice_id:
            continue
        payments = invoice.get("payments", [])
        remaining = [p for p in payments if p["id"] != payment_id]
        if len(remaining) == len(payments):
            return None
        invoice["payments"] = remaining
        if invoice.get("status") == "paid" and annotate_invoice(invoice)["balance_cents"] > 0:
            invoice["status"] = "sent"
        invoice["updated_at"] = _now()
        invoices[i] = invoice
        _save_invoices(store_user, workspace, book_id, invoices)
        return annotate_invoice(invoice)
    return None


# ---------------------------------------------------------------------------
# Accounts receivable rollup (computed on read)
# ---------------------------------------------------------------------------


def ar_summary(store_user: str, workspace: str, book_id: str) -> list[dict]:
    """Per-client: invoiced / paid / outstanding / overdue — 'who's behind'."""
    clients = {c["id"]: c for c in list_clients(store_user, workspace, book_id)}
    rollup: dict[str, dict] = {}
    for invoice in list_invoices(store_user, workspace, book_id):
        if invoice.get("status") == "void":
            continue
        cid = invoice.get("client_id") or ""
        entry = rollup.setdefault(
            cid,
            {
                "client_id": cid or None,
                "client_name": clients.get(cid, {}).get("name") or "(no client)",
                "invoiced_cents": 0,
                "paid_cents": 0,
                "outstanding_cents": 0,
                "overdue_cents": 0,
                "invoice_count": 0,
                "overdue_count": 0,
                "last_payment": None,
            },
        )
        entry["invoiced_cents"] += invoice["total_cents"]
        entry["paid_cents"] += invoice["paid_cents"]
        entry["outstanding_cents"] += max(invoice["balance_cents"], 0)
        entry["invoice_count"] += 1
        if invoice["overdue"]:
            entry["overdue_cents"] += invoice["balance_cents"]
            entry["overdue_count"] += 1
        for p in invoice.get("payments", []):
            if entry["last_payment"] is None or p["date"] > entry["last_payment"]:
                entry["last_payment"] = p["date"]
    out = list(rollup.values())
    out.sort(key=lambda e: (-e["overdue_cents"], -e["outstanding_cents"]))
    return out
