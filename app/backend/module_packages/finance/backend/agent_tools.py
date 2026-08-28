"""AI agent tools owned by the finance module — TOOL_SCHEMAS is folded into
_get_tools()'s returned list (filtered by disabled_modules first, then
list_finance_books/list_finance_transactions/get_finance_report/
get_budget_status/get_balance_projection additionally feed research_tools/
_READ_TOOLS via the manifest's read_only_agent_tools). execute() is what
agent_service.py's tool executor falls back to for any name its own core
match/case doesn't handle. Returning None means "not one of mine" so the
dispatcher can try the next module.

No admin-only Finance tool exists, so this manifest declares no
admin_agent_tools — every tool here resolves access the same way the
routers themselves do, through finance_service.find_book/resolve_caps,
never bypassing it."""

from datetime import datetime

TOOL_SCHEMAS = [
    {
        "name": "list_finance_books",
        "description": "List the finance books visible to the user in the active workspace, with their accounts, computed balances (integer cents) and categories. Call this first to get book/account IDs for other finance tools.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_finance_transactions",
        "description": "List transactions in a finance book, newest first. Amounts are integer cents: positive = income, negative = expense.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "to": {"type": "string", "description": "End date YYYY-MM-DD"},
                "account_id": {"type": "string", "description": "Filter to one account"},
                "category": {"type": "string", "description": "Filter to one category name"},
                "query": {"type": "string", "description": "Text match on payee/notes"},
                "limit": {"type": "integer", "description": "Max results (default 50)"},
            },
            "required": ["book_id"],
        },
    },
    {
        "name": "get_finance_report",
        "description": "Monthly income vs expenses report for a finance book with a per-category breakdown. Amounts are integer cents. Defaults to the current month when month is omitted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "month": {"type": "string", "description": "Month YYYY-MM (default: current)"},
            },
            "required": ["book_id"],
        },
    },
    {
        "name": "get_budget_status",
        "description": "Budget status for a finance book: spent vs limit per budgeted category for a month. Amounts are integer cents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "month": {"type": "string", "description": "Month YYYY-MM (default: current)"},
            },
            "required": ["book_id"],
        },
    },
    {
        "name": "get_balance_projection",
        "description": "Projected balance for a finance account on a future date: current balance plus scheduled recurring bills/income and planned one-off items up to that date. Returns the itemized breakdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "account_id": {"type": "string", "description": "Account ID within the book"},
                "date": {"type": "string", "description": "Target date YYYY-MM-DD"},
            },
            "required": ["book_id", "account_id", "date"],
        },
    },
    {
        "name": "create_invoice",
        "description": "Create a draft invoice in a finance book. Amounts are integer cents. Requires edit access to the book; the user must approve this write.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "client_id": {
                    "type": "string",
                    "description": "Optional client ID from the book's client list",
                },
                "due_date": {"type": "string", "description": "Due date YYYY-MM-DD"},
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "qty": {"type": "number"},
                            "unit_cents": {"type": "integer"},
                        },
                        "required": ["description", "unit_cents"],
                    },
                },
                "tax_pct": {"type": "number", "description": "Tax percent 0-50 (default 0)"},
                "notes": {"type": "string"},
            },
            "required": ["book_id", "due_date", "line_items"],
        },
    },
    {
        "name": "add_finance_transaction",
        "description": "Log an income or expense transaction in a finance book. amount_cents is signed integer cents: positive = income, negative = expense. Respects the user's access (contribute-level users may be limited to expenses). The user must approve this write.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book ID (see list_finance_books)"},
                "account_id": {"type": "string", "description": "Account ID within the book"},
                "amount_cents": {
                    "type": "integer",
                    "description": "Signed cents: -4599 = $45.99 expense",
                },
                "date": {"type": "string", "description": "Date YYYY-MM-DD (default today)"},
                "category": {"type": "string", "description": "Category from the book (optional)"},
                "payee": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["book_id", "account_id", "amount_cents"],
        },
    },
    {
        "name": "categorize_transaction",
        "description": "Set the category on an existing finance transaction (e.g. filing bank-imported uncategorized entries). Learns a payee rule so future imports auto-categorize. The user must approve this write.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
                "tx_id": {
                    "type": "string",
                    "description": "Transaction ID (see list_finance_transactions)",
                },
                "category": {"type": "string", "description": "Category name from the book"},
            },
            "required": ["book_id", "tx_id", "category"],
        },
    },
    {
        "name": "mark_invoice_paid",
        "description": "Record a payment on an invoice (partial or full — omit amount_cents to pay the remaining balance). Optionally logs a linked income transaction when account_id is given. Requires edit access; the user must approve this write.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
                "invoice_id": {"type": "string"},
                "amount_cents": {
                    "type": "integer",
                    "description": "Payment amount in cents (default: remaining balance)",
                },
                "account_id": {
                    "type": "string",
                    "description": "Optional account to log the income transaction in",
                },
                "method": {"type": "string", "description": "check / transfer / cash / card"},
            },
            "required": ["book_id", "invoice_id"],
        },
    },
]


def execute(name: str, inputs: dict, user: dict, workspace: str = "personal"):
    if name == "list_finance_books":
        from services import finance_service

        books = finance_service.list_visible_books(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
        )
        out = []
        for book in books:
            store = finance_service.store_for_annotated(book, user["name"], workspace)
            summary = finance_service.book_summary(store, workspace, book)
            # Share/audience fields are noise for the model
            slim = {
                k: v
                for k, v in book.items()
                if k not in ("shared_with", "contributors", "hidden_from")
            }
            slim["balances"] = summary["balances"]
            slim["total_cents"] = summary["total_cents"]
            out.append(slim)
        return out

    if name == "list_finance_transactions":
        from services import finance_service

        found_book = finance_service.find_book(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["book_id"],
        )
        if found_book is None:
            return {"error": f"Finance book {inputs['book_id']!r} not found"}
        store, book, _access = found_book
        items, total = finance_service.list_transactions(
            store,
            workspace,
            book["id"],
            date_from=inputs.get("from"),
            date_to=inputs.get("to"),
            account_id=inputs.get("account_id"),
            category=inputs.get("category"),
            query=inputs.get("query"),
            limit=min(int(inputs.get("limit") or 50), 200),
        )
        return {"items": items, "total": total}

    if name == "get_finance_report":
        from services import finance_service
        from module_packages.finance.backend import reports as finance_reports

        found_book = finance_service.find_book(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["book_id"],
        )
        if found_book is None:
            return {"error": f"Finance book {inputs['book_id']!r} not found"}
        store, book, _access = found_book
        month = inputs.get("month") or datetime.now().strftime("%Y-%m")
        return finance_reports.monthly_report(store, workspace, book, month)

    if name == "get_budget_status":
        from services import finance_planning_service, finance_service

        found_book = finance_service.find_book(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["book_id"],
        )
        if found_book is None:
            return {"error": f"Finance book {inputs['book_id']!r} not found"}
        store, book, _access = found_book
        month = inputs.get("month") or datetime.now().strftime("%Y-%m")
        return finance_planning_service.budget_status(store, workspace, book, month)

    if name == "get_balance_projection":
        from services import finance_planning_service, finance_service

        found_book = finance_service.find_book(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["book_id"],
        )
        if found_book is None:
            return {"error": f"Finance book {inputs['book_id']!r} not found"}
        store, book, _access = found_book
        return finance_planning_service.project_balance(
            store, workspace, book, inputs["account_id"], inputs["date"]
        )

    if name == "add_finance_transaction":
        from services import finance_planning_service, finance_service

        found_book = finance_service.find_book(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["book_id"],
        )
        if found_book is None:
            return {"error": f"Finance book {inputs['book_id']!r} not found"}
        store, book, access = found_book
        amount = inputs.get("amount_cents")
        if access == "contribute":
            caps = (
                finance_service.resolve_caps(
                    user["name"],
                    user.get("feature_role", "member"),
                    user.get("role") == "admin",
                    store,
                    book,
                    inputs.get("account_id"),
                    workspace,
                )
                or {}
            )
            kind = "income" if (amount or 0) > 0 else "expense"
            if kind not in caps.get("add", []):
                return {"error": f"Your access doesn't allow adding {kind} entries"}
        elif access != "edit":
            return {"error": "Read-only access — you cannot add transactions here"}
        tx = finance_service.add_transaction(
            store,
            workspace,
            book,
            {
                "date": inputs.get("date") or datetime.now().strftime("%Y-%m-%d"),
                "amount_cents": amount,
                "account_id": inputs.get("account_id"),
                "category": inputs.get("category", ""),
                "payee": inputs.get("payee", ""),
                "notes": inputs.get("notes", ""),
            },
            created_by=user["name"],
        )
        finance_planning_service.on_transactions_added(store, workspace, book["id"], [tx])
        return tx

    if name == "categorize_transaction":
        from services import finance_service

        found_book = finance_service.find_book(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["book_id"],
        )
        if found_book is None:
            return {"error": f"Finance book {inputs['book_id']!r} not found"}
        store, book, access = found_book
        tx = finance_service.get_transaction(store, workspace, book["id"], inputs["tx_id"])
        if not tx:
            return {"error": f"Transaction {inputs['tx_id']!r} not found"}
        if access == "contribute" and tx.get("created_by") != user["name"]:
            return {"error": "You can only categorize entries you created"}
        if access not in ("edit", "contribute"):
            return {"error": "Read-only access — you cannot categorize here"}
        result = finance_service.update_transaction(
            store, workspace, book, inputs["tx_id"], {"category": inputs["category"]}
        )
        if result and result.get("payee") and result.get("source") in ("simplefin", "csv"):
            finance_service.learn_rule(
                store, workspace, book["id"], result["payee"], inputs["category"]
            )
        return result or {"error": "Transaction not found"}

    if name == "create_invoice":
        from services import finance_invoice_service, finance_service

        found_book = finance_service.find_book(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["book_id"],
        )
        if found_book is None:
            return {"error": f"Finance book {inputs['book_id']!r} not found"}
        store, book, access = found_book
        if access != "edit":
            return {"error": "Read-only access — you cannot create invoices here"}
        return finance_invoice_service.create_invoice(
            store,
            workspace,
            book["id"],
            {
                "client_id": inputs.get("client_id"),
                "due_date": inputs["due_date"],
                "line_items": inputs.get("line_items") or [],
                "tax_pct": inputs.get("tax_pct", 0),
                "notes": inputs.get("notes", ""),
            },
            created_by=user["name"],
        )

    if name == "mark_invoice_paid":
        from services import finance_invoice_service, finance_service

        found_book = finance_service.find_book(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["book_id"],
        )
        if found_book is None:
            return {"error": f"Finance book {inputs['book_id']!r} not found"}
        store, book, access = found_book
        if access != "edit":
            return {"error": "Read-only access — you cannot record payments here"}
        invoice = finance_invoice_service.get_invoice(
            store, workspace, book["id"], inputs["invoice_id"]
        )
        if not invoice:
            return {"error": f"Invoice {inputs['invoice_id']!r} not found"}
        amount = inputs.get("amount_cents") or invoice["balance_cents"]
        if amount <= 0:
            return {"error": "Invoice already has a zero balance"}
        return finance_invoice_service.record_payment(
            store,
            workspace,
            book["id"],
            inputs["invoice_id"],
            {
                "amount_cents": amount,
                "account_id": inputs.get("account_id"),
                "method": inputs.get("method", ""),
            },
            created_by=user["name"],
        )

    return None
