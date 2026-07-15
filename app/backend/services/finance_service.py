"""Finance module core: books, accounts, categories, transactions, balances.

Storage (workspace-scoped via ws_path):
  {ws_path}/Finance/books.json                                — book registry
  {ws_path}/Finance/books/{book_id}/transactions_{YYYY}.json  — per-year shards

A "store" is either a real user's own Brain (per workspace) or a pool
pseudo-user (_household for the personal workspace, _team for business).
Pool files always live at the pseudo-user's personal base path.

Money is signed integer cents everywhere: amount_cents > 0 is income,
amount_cents < 0 is expense. Balances are always computed on read
(opening_balance_cents + sum of shard amounts) — never stored.

Access resolution: _resolve_book_access() is the single gate every router
path and agent tool must go through. Phase A grants: own store = edit,
pool = read (admin edit). Shares/contributors/caps extend this function
in the sharing phase — signatures already carry viewer_role for that.
"""

import uuid
from datetime import date, datetime, timezone

from services.file_service import (
    finance_book_dir,
    finance_books_path,
    finance_rules_path,
    finance_tx_path,
    read_json,
    write_json,
)

POOL_HOUSEHOLD = "_household"
POOL_TEAM = "_team"

ACCOUNT_TYPES = {"checking", "savings", "credit", "cash", "other"}
CATEGORY_KINDS = {"expense", "income"}

# Workspace-aware seed categories. Personal keeps Groceries + Salary (relied on by
# existing tests / muscle memory); business gets accounting-flavored buckets.
_PERSONAL_CATEGORIES = [
    {"name": "Groceries", "kind": "expense"},
    {"name": "Housing", "kind": "expense"},
    {"name": "Transportation", "kind": "expense"},
    {"name": "Utilities", "kind": "expense"},
    {"name": "Dining", "kind": "expense"},
    {"name": "Health", "kind": "expense"},
    {"name": "Shopping", "kind": "expense"},
    {"name": "Entertainment", "kind": "expense"},
    {"name": "Insurance", "kind": "expense"},
    {"name": "Other", "kind": "expense"},
    {"name": "Salary", "kind": "income"},
    {"name": "Freelance", "kind": "income"},
    {"name": "Investments", "kind": "income"},
    {"name": "Interest", "kind": "income"},
    {"name": "Gifts", "kind": "income"},
    {"name": "Refunds", "kind": "income"},
    {"name": "Other Income", "kind": "income"},
]

_BUSINESS_CATEGORIES = [
    {"name": "Payroll", "kind": "expense"},
    {"name": "Contractors", "kind": "expense"},
    {"name": "Software/SaaS", "kind": "expense"},
    {"name": "Advertising", "kind": "expense"},
    {"name": "Office/Rent", "kind": "expense"},
    {"name": "Supplies", "kind": "expense"},
    {"name": "Travel", "kind": "expense"},
    {"name": "Meals", "kind": "expense"},
    {"name": "Equipment", "kind": "expense"},
    {"name": "Professional Services", "kind": "expense"},
    {"name": "Other", "kind": "expense"},
    {"name": "Product Sales", "kind": "income"},
    {"name": "Services", "kind": "income"},
    {"name": "Consulting", "kind": "income"},
    {"name": "Interest", "kind": "income"},
    {"name": "Other Income", "kind": "income"},
]

# Back-compat alias (personal set) for any external importer of this name.
DEFAULT_CATEGORIES = _PERSONAL_CATEGORIES

_PERSONAL_TAX_BUCKETS = ["Medical", "Charitable", "Business Expense", "Education"]
_BUSINESS_TAX_BUCKETS = [
    "Advertising",
    "Supplies",
    "Travel",
    "Meals",
    "Home Office",
    "Equipment",
    "Contract Labor",
    "Vehicle/Mileage",
]


def default_categories(workspace: str) -> list[dict]:
    """Workspace-aware seed categories for a new book (business vs personal)."""
    src = _BUSINESS_CATEGORIES if workspace == "business" else _PERSONAL_CATEGORIES
    return [dict(c) for c in src]


def default_tax_categories(workspace: str) -> list[str]:
    """Workspace-aware seed tax buckets for a new book."""
    return list(_BUSINESS_TAX_BUCKETS if workspace == "business" else _PERSONAL_TAX_BUCKETS)


# Guard against absurd amounts (1 trillion dollars in cents)
MAX_AMOUNT_CENTS = 10**14


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_pool(store_user: str) -> bool:
    return store_user in (POOL_HOUSEHOLD, POOL_TEAM)


def pool_for(workspace: str) -> str:
    return POOL_TEAM if workspace == "business" else POOL_HOUSEHOLD


def store_workspace(store_user: str, workspace: str) -> str:
    """Pool pseudo-users keep their files at their personal base path."""
    return "personal" if is_pool(store_user) else workspace


# ---------------------------------------------------------------------------
# Registry load/save
# ---------------------------------------------------------------------------


def _load(store_user: str, workspace: str) -> dict:
    ws = store_workspace(store_user, workspace)
    return read_json(finance_books_path(store_user, ws), default={"books": []})


def _save(store_user: str, workspace: str, data: dict) -> None:
    ws = store_workspace(store_user, workspace)
    write_json(finance_books_path(store_user, ws), data)


def list_books(store_user: str, workspace: str) -> list[dict]:
    return _load(store_user, workspace).get("books", [])


def get_book(store_user: str, workspace: str, book_id: str) -> dict | None:
    return next((b for b in list_books(store_user, workspace) if b["id"] == book_id), None)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid date: {value!r} (expected YYYY-MM-DD)")


def _validate_amount(amount_cents) -> int:
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
        raise ValueError("amount_cents must be an integer (cents)")
    if amount_cents == 0:
        raise ValueError("amount_cents cannot be zero")
    if abs(amount_cents) > MAX_AMOUNT_CENTS:
        raise ValueError("amount_cents is out of range")
    return amount_cents


def _validate_categories(categories: list[dict]) -> list[dict]:
    seen = set()
    cleaned = []
    for cat in categories:
        name = (cat.get("name") or "").strip()
        kind = cat.get("kind", "expense")
        if not name or len(name) > 40:
            raise ValueError("Category names must be 1-40 characters")
        if kind not in CATEGORY_KINDS:
            raise ValueError(f"Invalid category kind: {kind!r}")
        if name.lower() in seen:
            raise ValueError(f"Duplicate category: {name}")
        seen.add(name.lower())
        cleaned.append({"name": name, "kind": kind})
    return cleaned


def _require_category(book: dict, name: str) -> str:
    if name == "":
        return name  # uncategorized — always allowed
    if not any(c["name"] == name for c in book.get("categories", [])):
        raise ValueError(f"Unknown category: {name!r}")
    return name


def _require_account(book: dict, account_id: str) -> dict:
    account = next((a for a in book.get("accounts", []) if a["id"] == account_id), None)
    if not account:
        raise ValueError("Unknown account")
    return account


# ---------------------------------------------------------------------------
# Access resolution — THE single gate (extended by the sharing phase)
# ---------------------------------------------------------------------------


# Missing caps on a contribute entry = the employee expense-submission case:
# add expenses only, edit own entries, no balances, own entries only.
DEFAULT_CAPS = {"add": ["expense"], "edit_own": True, "see_balances": False, "see_all_tx": False}
ACCESS_LEVELS = {"read", "contribute", "edit"}


def normalize_caps(caps) -> dict:
    if not isinstance(caps, dict):
        return dict(DEFAULT_CAPS)
    add = caps.get("add", DEFAULT_CAPS["add"])
    if not isinstance(add, list):
        add = list(DEFAULT_CAPS["add"])
    add = [a for a in add if a in ("expense", "income")]
    return {
        "add": add,
        "edit_own": bool(caps.get("edit_own", DEFAULT_CAPS["edit_own"])),
        "see_balances": bool(caps.get("see_balances", DEFAULT_CAPS["see_balances"])),
        "see_all_tx": bool(caps.get("see_all_tx", DEFAULT_CAPS["see_all_tx"])),
    }


def _union_caps(caps_list: list[dict]) -> dict:
    out = {"add": [], "edit_own": False, "see_balances": False, "see_all_tx": False}
    for caps in caps_list:
        out["add"] = sorted(set(out["add"]) | set(caps.get("add", [])))
        for key in ("edit_own", "see_balances", "see_all_tx"):
            out[key] = out[key] or caps.get(key, False)
    return out


def _entry_matches(entry: dict, viewer: str, viewer_role: str, workspace: str) -> bool:
    target = entry.get("target") or ""
    if target == viewer:
        return True
    if target == "team":
        return workspace == "business"
    if target == "household":
        return True
    if target.startswith("role:"):
        return target[5:] == viewer_role
    return False


def _entry_accepted(entry: dict, viewer: str) -> bool:
    accepted = entry.get("accepted")
    if accepted is None:
        return True  # legacy/open entry (pool contributors never carry accepted)
    return viewer in accepted


def _rung_result(entries: list[dict]) -> tuple[str, dict | None] | None:
    """Resolve one specificity rung: edit > contribute (caps union) > read."""
    if not entries:
        return None
    if any(e.get("access", "read") == "edit" for e in entries):
        return ("edit", None)
    contribs = [e for e in entries if e.get("access", "read") == "contribute"]
    if contribs:
        return ("contribute", _union_caps([normalize_caps(e.get("caps")) for e in contribs]))
    return ("read", None)


def _account_of(book: dict, account_id: str | None) -> dict | None:
    if not account_id:
        return None
    return next((a for a in book.get("accounts", []) if a["id"] == account_id), None)


def _resolve_book_access(
    viewer: str,
    viewer_role: str,
    is_admin: bool,
    store_user: str,
    book: dict,
    account_id: str | None = None,
    workspace: str = "personal",
) -> tuple[str | None, dict | None]:
    """THE single access gate. Returns (access, caps):
    access ∈ {"edit", "contribute", "read", None}; caps only for contribute.

    Specificity ladders (a by-name entry fully overrides group/role entries,
    consistent with the Assets rule):
      personal shares:  account by-name > account group > book by-name > book group
      pool books:       admin > account by-name > book by-name >
                        account group > book group > workspace read
    hidden_from (names + role:<r>) beats shares for everyone except the owner
    and pool admins. Personal share entries require the accept handshake;
    pool contributor entries never do (pool books are workspace-visible).
    """
    hidden = book.get("hidden_from") or []
    is_hidden = viewer in hidden or f"role:{viewer_role}" in hidden

    if is_pool(store_user):
        if is_admin:
            return ("edit", None)
        if is_hidden:
            return (None, None)
        account = _account_of(book, account_id)
        acct_entries = [
            e
            for e in (account.get("contributors") or [] if account else [])
            if _entry_matches(e, viewer, viewer_role, workspace)
        ]
        book_entries = [
            e
            for e in (book.get("contributors") or [])
            if _entry_matches(e, viewer, viewer_role, workspace)
        ]
        for rung in (
            [e for e in acct_entries if e.get("target") == viewer],
            [e for e in book_entries if e.get("target") == viewer],
            [e for e in acct_entries if e.get("target") != viewer],
            [e for e in book_entries if e.get("target") != viewer],
        ):
            result = _rung_result(rung)
            if result:
                return result
        return ("read", None)

    if store_user == viewer:
        return ("edit", None)

    if is_hidden:
        return (None, None)

    account = _account_of(book, account_id)
    acct_entries = [
        e
        for e in (account.get("shared_with") or [] if account else [])
        if _entry_matches(e, viewer, viewer_role, workspace) and _entry_accepted(e, viewer)
    ]
    book_entries = [
        e
        for e in (book.get("shared_with") or [])
        if _entry_matches(e, viewer, viewer_role, workspace) and _entry_accepted(e, viewer)
    ]
    for rung in (
        [e for e in acct_entries if e.get("target") == viewer],
        [e for e in acct_entries if e.get("target") != viewer],
        [e for e in book_entries if e.get("target") == viewer],
        [e for e in book_entries if e.get("target") != viewer],
    ):
        result = _rung_result(rung)
        if result:
            return result
    return (None, None)


def resolve_caps(
    viewer: str,
    viewer_role: str,
    is_admin: bool,
    store_user: str,
    book: dict,
    account_id: str | None = None,
    workspace: str = "personal",
) -> dict | None:
    """Caps for a contribute-level viewer (None for read/edit/owner)."""
    _access, caps = _resolve_book_access(
        viewer, viewer_role, is_admin, store_user, book, account_id, workspace
    )
    return caps


def store_for_annotated(book: dict, viewer: str, workspace: str) -> str:
    """Map an annotated book (from list_visible_books) back to its store user."""
    owner = book.get("_owner")
    if owner == "household":
        return POOL_HOUSEHOLD
    if owner == "team":
        return POOL_TEAM
    return owner or viewer


def annotate(
    book: dict, store_user: str, viewer: str, access: str, caps: dict | None = None
) -> dict:
    """Attach _owner/_access/_caps the way Assets does, so the frontend can gate UI.

    Own-store books carry no _owner (absence = "mine")."""
    out = dict(book)
    if store_user == POOL_HOUSEHOLD:
        out["_owner"] = "household"
    elif store_user == POOL_TEAM:
        out["_owner"] = "team"
    elif store_user != viewer:
        out["_owner"] = store_user
    out["_access"] = access
    if caps is not None:
        out["_caps"] = caps
    return out


def list_visible_books(
    viewer: str,
    viewer_role: str,
    is_admin: bool,
    workspace: str,
    include_archived: bool = False,
) -> list[dict]:
    """Own + workspace-pool + shared-to-me books, annotated _owner/_access/_caps.

    Cross-store scanning is routed through the share index so only owners who
    actually share something with this viewer are read."""
    from services.finance_index import sharers_for

    results = []
    stores = [viewer, pool_for(workspace)]
    stores += [s for s in sharers_for(viewer, viewer_role, workspace) if s not in stores]
    for store_user in stores:
        for book in list_books(store_user, workspace):
            if book.get("archived") and not include_archived:
                continue
            access, caps = _resolve_book_access(
                viewer, viewer_role, is_admin, store_user, book, workspace=workspace
            )
            if not access:
                continue
            results.append(annotate(book, store_user, viewer, access, caps))
    return results


def find_book(
    viewer: str,
    viewer_role: str,
    is_admin: bool,
    workspace: str,
    book_id: str,
) -> tuple[str, dict, str] | None:
    """Locate a book the viewer can access. Returns (store_user, book, access).

    Callers that need contribute caps call resolve_caps() with the result."""
    from services.finance_index import sharers_for

    stores = [viewer, pool_for(workspace)]
    stores += [s for s in sharers_for(viewer, viewer_role, workspace) if s not in stores]
    for store_user in stores:
        book = get_book(store_user, workspace, book_id)
        if book:
            access, _caps = _resolve_book_access(
                viewer, viewer_role, is_admin, store_user, book, workspace=workspace
            )
            return (store_user, book, access) if access else None
    return None


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------


def create_book(
    store_user: str,
    workspace: str,
    name: str,
    created_by: str,
    icon: str = "",
    currency: str = "USD",
    categories: list[dict] | None = None,
) -> dict:
    name = (name or "").strip()
    if not name or len(name) > 80:
        raise ValueError("Book name must be 1-80 characters")
    currency = (currency or "USD").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("Currency must be a 3-letter code")
    cats = _validate_categories(categories) if categories else default_categories(workspace)

    book = {
        "id": str(uuid.uuid4()),
        "name": name,
        "icon": icon or "💰",
        "currency": currency,
        "categories": cats,
        "tax_categories": default_tax_categories(workspace),
        "budget_warn_pct": 80,
        "accounts": [],
        "shared_with": [],
        "contributors": [],
        "hidden_from": [],
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
        "archived": False,
    }
    data = _load(store_user, workspace)
    data.setdefault("books", []).append(book)
    _save(store_user, workspace, data)
    return book


def update_book(store_user: str, workspace: str, book_id: str, updates: dict) -> dict | None:
    data = _load(store_user, workspace)
    for i, book in enumerate(data.get("books", [])):
        if book["id"] != book_id:
            continue
        allowed: dict = {}
        if "name" in updates:
            name = (updates["name"] or "").strip()
            if not name or len(name) > 80:
                raise ValueError("Book name must be 1-80 characters")
            allowed["name"] = name
        if "icon" in updates:
            allowed["icon"] = (updates["icon"] or "💰")[:8]
        if "currency" in updates:
            currency = (updates["currency"] or "USD").strip().upper()
            if len(currency) != 3 or not currency.isalpha():
                raise ValueError("Currency must be a 3-letter code")
            allowed["currency"] = currency
        if "budget_warn_pct" in updates:
            pct = updates["budget_warn_pct"]
            if isinstance(pct, bool) or not isinstance(pct, int) or not 1 <= pct <= 100:
                raise ValueError("budget_warn_pct must be 1-100")
            allowed["budget_warn_pct"] = pct
        if "archived" in updates:
            allowed["archived"] = bool(updates["archived"])
        if "invoice_prefix" in updates:
            prefix = (updates["invoice_prefix"] or "INV").strip().upper()
            if not prefix or len(prefix) > 10 or not prefix.isalnum():
                raise ValueError("invoice_prefix must be 1-10 alphanumeric characters")
            allowed["invoice_prefix"] = prefix
        if "tax_categories" in updates:
            tax = updates["tax_categories"]
            if not isinstance(tax, list) or any(
                not isinstance(t, str) or not t.strip() or len(t) > 60 for t in tax
            ):
                raise ValueError("tax_categories must be a list of short names")
            allowed["tax_categories"] = [t.strip() for t in tax]
        if "categories" in updates:
            # handled through set_categories so removed names re-label transactions
            allowed["categories"] = _apply_categories(
                store_user, workspace, book, _validate_categories(updates["categories"])
            )
        allowed["updated_at"] = _now()
        data["books"][i] = {**book, **allowed}
        _save(store_user, workspace, data)
        return data["books"][i]
    return None


def _apply_categories(
    store_user: str, workspace: str, book: dict, new_categories: list[dict]
) -> list[dict]:
    """Re-label transactions of removed categories to "" (uncategorized)."""
    old_names = {c["name"] for c in book.get("categories", [])}
    new_names = {c["name"] for c in new_categories}
    removed = old_names - new_names
    if removed:
        ws = store_workspace(store_user, workspace)
        for year in _shard_years(store_user, workspace, book["id"]):
            path = finance_tx_path(store_user, book["id"], year, ws)
            shard = read_json(path, default={"transactions": []})
            changed = False
            for tx in shard.get("transactions", []):
                if tx.get("category") in removed:
                    tx["category"] = ""
                    changed = True
            if changed:
                write_json(path, shard)
    return new_categories


def delete_book(store_user: str, workspace: str, book_id: str) -> bool:
    data = _load(store_user, workspace)
    books = data.get("books", [])
    if not any(b["id"] == book_id for b in books):
        return False
    data["books"] = [b for b in books if b["id"] != book_id]
    _save(store_user, workspace, data)
    # Remove the book's data directory (shards). Receipts arrive in a later
    # phase and live under the same dir, so this covers them too.
    ws = store_workspace(store_user, workspace)
    book_dir = finance_book_dir(store_user, book_id, ws)
    if book_dir.exists():
        import shutil

        shutil.rmtree(book_dir, ignore_errors=True)
    return True


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def add_account(store_user: str, workspace: str, book_id: str, account_data: dict) -> dict | None:
    data = _load(store_user, workspace)
    for i, book in enumerate(data.get("books", [])):
        if book["id"] != book_id:
            continue
        name = (account_data.get("name") or "").strip()
        if not name or len(name) > 60:
            raise ValueError("Account name must be 1-60 characters")
        acct_type = account_data.get("type", "checking")
        if acct_type not in ACCOUNT_TYPES:
            raise ValueError(f"Invalid account type: {acct_type!r}")
        opening = account_data.get("opening_balance_cents", 0)
        if isinstance(opening, bool) or not isinstance(opening, int):
            raise ValueError("opening_balance_cents must be an integer (cents)")
        opening_date = account_data.get("opening_date")
        if opening_date:
            _parse_date(opening_date)
        account = {
            "id": str(uuid.uuid4()),
            "name": name,
            "type": acct_type,
            "opening_balance_cents": opening,
            "opening_date": opening_date,
            "deviation_threshold_cents": None,
            "synced_balance_cents": None,
            "synced_at": None,
            "simplefin_account_id": None,
            "last_deviation_alert": None,
            "archived": False,
            "shared_with": [],
            "contributors": [],
        }
        book.setdefault("accounts", []).append(account)
        book["updated_at"] = _now()
        data["books"][i] = book
        _save(store_user, workspace, data)
        return account
    return None


def update_account(
    store_user: str, workspace: str, book_id: str, account_id: str, updates: dict
) -> dict | None:
    data = _load(store_user, workspace)
    for i, book in enumerate(data.get("books", [])):
        if book["id"] != book_id:
            continue
        for j, account in enumerate(book.get("accounts", [])):
            if account["id"] != account_id:
                continue
            allowed: dict = {}
            if "name" in updates:
                name = (updates["name"] or "").strip()
                if not name or len(name) > 60:
                    raise ValueError("Account name must be 1-60 characters")
                allowed["name"] = name
            if "type" in updates:
                if updates["type"] not in ACCOUNT_TYPES:
                    raise ValueError(f"Invalid account type: {updates['type']!r}")
                allowed["type"] = updates["type"]
            if "opening_balance_cents" in updates:
                opening = updates["opening_balance_cents"]
                if isinstance(opening, bool) or not isinstance(opening, int):
                    raise ValueError("opening_balance_cents must be an integer (cents)")
                allowed["opening_balance_cents"] = opening
            if "opening_date" in updates:
                if updates["opening_date"]:
                    _parse_date(updates["opening_date"])
                allowed["opening_date"] = updates["opening_date"]
            if "deviation_threshold_cents" in updates:
                threshold = updates["deviation_threshold_cents"]
                if threshold is not None and (
                    isinstance(threshold, bool) or not isinstance(threshold, int) or threshold <= 0
                ):
                    raise ValueError("deviation_threshold_cents must be a positive integer")
                allowed["deviation_threshold_cents"] = threshold
            if "archived" in updates:
                allowed["archived"] = bool(updates["archived"])
            if "synced_balance_cents" in updates:
                synced = updates["synced_balance_cents"]
                if synced is not None and (isinstance(synced, bool) or not isinstance(synced, int)):
                    raise ValueError("synced_balance_cents must be an integer (cents)")
                allowed["synced_balance_cents"] = synced
                allowed["synced_at"] = _now()
            book["accounts"][j] = {**account, **allowed}
            book["updated_at"] = _now()
            data["books"][i] = book
            _save(store_user, workspace, data)
            return book["accounts"][j]
        return None
    return None


def delete_account(store_user: str, workspace: str, book_id: str, account_id: str) -> bool:
    """Remove an account. Callers must first check account_has_transactions()."""
    data = _load(store_user, workspace)
    for i, book in enumerate(data.get("books", [])):
        if book["id"] != book_id:
            continue
        accounts = book.get("accounts", [])
        if not any(a["id"] == account_id for a in accounts):
            return False
        book["accounts"] = [a for a in accounts if a["id"] != account_id]
        book["updated_at"] = _now()
        data["books"][i] = book
        _save(store_user, workspace, data)
        return True
    return False


# ---------------------------------------------------------------------------
# Transactions (per-book per-year shards)
# ---------------------------------------------------------------------------


def _fresh_book(store_user: str, workspace: str, book_or_id: dict | str) -> dict:
    """Always validate against the current on-disk book — callers may hold a
    stale dict from before an account/category change."""
    book_id = book_or_id["id"] if isinstance(book_or_id, dict) else book_or_id
    book = get_book(store_user, workspace, book_id)
    if not book:
        raise ValueError("Book not found")
    return book


def fresh_book(store_user: str, workspace: str, book_or_id: dict | str) -> dict:
    """Public re-load — other finance services validate against current state."""
    return _fresh_book(store_user, workspace, book_or_id)


def _shard_years(store_user: str, workspace: str, book_id: str) -> list[int]:
    ws = store_workspace(store_user, workspace)
    book_dir = finance_book_dir(store_user, book_id, ws)
    if not book_dir.exists():
        return []
    years = []
    for f in book_dir.glob("transactions_*.json"):
        try:
            years.append(int(f.stem.split("_")[1]))
        except (IndexError, ValueError):
            continue
    return sorted(years)


def _read_shard(store_user: str, workspace: str, book_id: str, year: int) -> dict:
    ws = store_workspace(store_user, workspace)
    return read_json(finance_tx_path(store_user, book_id, year, ws), default={"transactions": []})


def _write_shard(store_user: str, workspace: str, book_id: str, year: int, shard: dict) -> None:
    ws = store_workspace(store_user, workspace)
    write_json(finance_tx_path(store_user, book_id, year, ws), shard)


def has_transactions(store_user: str, workspace: str, book_id: str) -> bool:
    for year in _shard_years(store_user, workspace, book_id):
        if _read_shard(store_user, workspace, book_id, year).get("transactions"):
            return True
    return False


def account_has_transactions(
    store_user: str, workspace: str, book_id: str, account_id: str
) -> bool:
    for year in _shard_years(store_user, workspace, book_id):
        shard = _read_shard(store_user, workspace, book_id, year)
        if any(t.get("account_id") == account_id for t in shard.get("transactions", [])):
            return True
    return False


def list_transactions(
    store_user: str,
    workspace: str,
    book_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    account_id: str | None = None,
    category: str | None = None,
    query: str | None = None,
    created_by: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Filtered, newest-first transactions. Returns (page, total_matching)."""
    if date_from:
        _parse_date(date_from)
    if date_to:
        _parse_date(date_to)
    year_from = int(date_from[:4]) if date_from else None
    year_to = int(date_to[:4]) if date_to else None

    matches: list[dict] = []
    for year in _shard_years(store_user, workspace, book_id):
        if year_from and year < year_from:
            continue
        if year_to and year > year_to:
            continue
        for tx in _read_shard(store_user, workspace, book_id, year).get("transactions", []):
            if date_from and tx["date"] < date_from:
                continue
            if date_to and tx["date"] > date_to:
                continue
            if account_id and tx.get("account_id") != account_id:
                continue
            if category is not None and tx.get("category", "") != category:
                continue
            if created_by is not None and tx.get("created_by") != created_by:
                continue
            if query:
                haystack = f"{tx.get('payee', '')} {tx.get('notes', '')}".lower()
                if query.lower() not in haystack:
                    continue
            matches.append(tx)

    matches.sort(key=lambda t: (t["date"], t.get("created_at", "")), reverse=True)
    return matches[offset : offset + limit], len(matches)


def get_transaction(store_user: str, workspace: str, book_id: str, tx_id: str) -> dict | None:
    for year in _shard_years(store_user, workspace, book_id):
        shard = _read_shard(store_user, workspace, book_id, year)
        for tx in shard.get("transactions", []):
            if tx["id"] == tx_id:
                return tx
    return None


def add_transaction(
    store_user: str,
    workspace: str,
    book_or_id: dict | str,
    tx_data: dict,
    created_by: str,
    source: str = "manual",
) -> dict:
    book = _fresh_book(store_user, workspace, book_or_id)
    tx_date = _parse_date(tx_data.get("date") or "")
    amount = _validate_amount(tx_data.get("amount_cents"))
    account = _require_account(book, tx_data.get("account_id") or "")
    if account.get("archived"):
        raise ValueError("Cannot add transactions to an archived account")
    category = _require_category(book, tx_data.get("category", ""))

    tx = {
        "id": str(uuid.uuid4()),
        "date": tx_date.isoformat(),
        "amount_cents": amount,
        "account_id": account["id"],
        "category": category,
        "payee": (tx_data.get("payee") or "").strip()[:120],
        "payee_contact_id": (tx_data.get("payee_contact_id") or None) or None,
        "notes": (tx_data.get("notes") or "").strip()[:2000],
        "deductible": bool(tx_data.get("deductible", False)),
        "tax_category": tx_data.get("tax_category"),
        "source": source,
        "simplefin_id": tx_data.get("simplefin_id"),
        "import_hash": tx_data.get("import_hash"),
        "pending": bool(tx_data.get("pending", False)),
        "attachments": [],
        "invoice_id": tx_data.get("invoice_id"),
        "client_id": tx_data.get("client_id"),
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
    }
    shard = _read_shard(store_user, workspace, book["id"], tx_date.year)
    shard.setdefault("transactions", []).append(tx)
    _write_shard(store_user, workspace, book["id"], tx_date.year, shard)
    return tx


def update_transaction(
    store_user: str, workspace: str, book_or_id: dict | str, tx_id: str, updates: dict
) -> dict | None:
    book = _fresh_book(store_user, workspace, book_or_id)
    for year in _shard_years(store_user, workspace, book["id"]):
        shard = _read_shard(store_user, workspace, book["id"], year)
        transactions = shard.get("transactions", [])
        for i, tx in enumerate(transactions):
            if tx["id"] != tx_id:
                continue
            allowed: dict = {}
            if "date" in updates:
                allowed["date"] = _parse_date(updates["date"]).isoformat()
            if "amount_cents" in updates:
                allowed["amount_cents"] = _validate_amount(updates["amount_cents"])
            if "account_id" in updates:
                account = _require_account(book, updates["account_id"])
                allowed["account_id"] = account["id"]
            if "category" in updates:
                allowed["category"] = _require_category(book, updates["category"])
            if "payee" in updates:
                allowed["payee"] = (updates["payee"] or "").strip()[:120]
            if "payee_contact_id" in updates:
                allowed["payee_contact_id"] = (updates["payee_contact_id"] or None) or None
            if "notes" in updates:
                allowed["notes"] = (updates["notes"] or "").strip()[:2000]
            if "deductible" in updates:
                allowed["deductible"] = bool(updates["deductible"])
            if "tax_category" in updates:
                allowed["tax_category"] = updates["tax_category"]
            allowed["updated_at"] = _now()
            updated = {**tx, **allowed}

            new_year = int(updated["date"][:4])
            if new_year != year:
                # Date moved across a year boundary — move between shards
                transactions.pop(i)
                _write_shard(store_user, workspace, book["id"], year, shard)
                dest = _read_shard(store_user, workspace, book["id"], new_year)
                dest.setdefault("transactions", []).append(updated)
                _write_shard(store_user, workspace, book["id"], new_year, dest)
            else:
                transactions[i] = updated
                _write_shard(store_user, workspace, book["id"], year, shard)
            return updated
    return None


def delete_transaction(store_user: str, workspace: str, book_id: str, tx_id: str) -> bool:
    for year in _shard_years(store_user, workspace, book_id):
        shard = _read_shard(store_user, workspace, book_id, year)
        transactions = shard.get("transactions", [])
        remaining = [t for t in transactions if t["id"] != tx_id]
        if len(remaining) != len(transactions):
            shard["transactions"] = remaining
            _write_shard(store_user, workspace, book_id, year, shard)
            receipts = _receipts_dir(store_user, workspace, book_id, tx_id)
            if receipts.exists():
                import shutil

                shutil.rmtree(receipts, ignore_errors=True)
            return True
    return False


# ---------------------------------------------------------------------------
# Balances (always computed, never stored)
# ---------------------------------------------------------------------------


def account_balances(store_user: str, workspace: str, book: dict) -> dict[str, int]:
    totals = {a["id"]: a.get("opening_balance_cents", 0) for a in book.get("accounts", [])}
    for year in _shard_years(store_user, workspace, book["id"]):
        for tx in _read_shard(store_user, workspace, book["id"], year).get("transactions", []):
            if tx.get("account_id") in totals:
                totals[tx["account_id"]] += tx.get("amount_cents", 0)
    return totals


def book_summary(store_user: str, workspace: str, book: dict) -> dict:
    balances = account_balances(store_user, workspace, book)
    active_total = sum(balances[a["id"]] for a in book.get("accounts", []) if not a.get("archived"))
    return {"balances": balances, "total_cents": active_total}


# ---------------------------------------------------------------------------
# Bulk import (SimpleFIN sync + CSV) — one shard write per year, not per tx
# ---------------------------------------------------------------------------


def _suggest_payee_contact(store_user: str, workspace: str, payee: str) -> str | None:
    """Best-effort: match an imported payee string to a CRM contact so bank/CSV
    transactions auto-link. Never raises — Finance must work without Contacts."""
    if not payee or is_pool(store_user):
        return None
    try:
        from services import contacts_service

        match = contacts_service.find_match(store_user, workspace, name=payee)
        return match["id"] if match else None
    except Exception:
        return None


def bulk_add_transactions(
    store_user: str,
    workspace: str,
    book_or_id: dict | str,
    tx_datas: list[dict],
    created_by: str,
    source: str,
) -> list[dict]:
    """Validate + append many transactions, grouped by year shard.

    Callers are responsible for dedup (simplefin_id / import_hash) BEFORE
    calling. Raises ValueError on the first invalid record — all-or-nothing
    per call, so import previews should pre-validate."""
    book = _fresh_book(store_user, workspace, book_or_id)
    records: list[dict] = []
    for tx_data in tx_datas:
        tx_date = _parse_date(tx_data.get("date") or "")
        amount = _validate_amount(tx_data.get("amount_cents"))
        account = _require_account(book, tx_data.get("account_id") or "")
        if account.get("archived"):
            raise ValueError("Cannot add transactions to an archived account")
        category = _require_category(book, tx_data.get("category", ""))
        payee = (tx_data.get("payee") or "").strip()[:120]
        records.append(
            {
                "id": str(uuid.uuid4()),
                "date": tx_date.isoformat(),
                "amount_cents": amount,
                "account_id": account["id"],
                "category": category,
                "payee": payee,
                "payee_contact_id": _suggest_payee_contact(store_user, workspace, payee),
                "notes": (tx_data.get("notes") or "").strip()[:2000],
                "deductible": False,
                "tax_category": None,
                "source": source,
                "simplefin_id": tx_data.get("simplefin_id"),
                "import_hash": tx_data.get("import_hash"),
                "pending": bool(tx_data.get("pending", False)),
                "attachments": [],
                "invoice_id": None,
                "client_id": None,
                "created_by": created_by,
                "created_at": _now(),
                "updated_at": _now(),
            }
        )
    by_year: dict[int, list[dict]] = {}
    for rec in records:
        by_year.setdefault(int(rec["date"][:4]), []).append(rec)
    for year, recs in by_year.items():
        shard = _read_shard(store_user, workspace, book["id"], year)
        shard.setdefault("transactions", []).extend(recs)
        _write_shard(store_user, workspace, book["id"], year, shard)
    return records


def existing_dedup_keys(store_user: str, workspace: str, book_id: str) -> tuple[set, set]:
    """(simplefin_ids, import_hashes) already present in a book — for import dedup."""
    sf_ids: set = set()
    hashes: set = set()
    for year in _shard_years(store_user, workspace, book_id):
        for tx in _read_shard(store_user, workspace, book_id, year).get("transactions", []):
            if tx.get("simplefin_id"):
                sf_ids.add(tx["simplefin_id"])
            if tx.get("import_hash"):
                hashes.add(tx["import_hash"])
    return sf_ids, hashes


def set_account_sync_state(
    store_user: str,
    workspace: str,
    book_id: str,
    account_id: str,
    synced_balance_cents: int | None,
    simplefin_account_id: str | None = None,
) -> None:
    """Record the bank-reported balance on an account. This is SOURCE data from
    the bank (used by deviation checks) — not a derived value."""
    data = _load(store_user, workspace)
    for i, book in enumerate(data.get("books", [])):
        if book["id"] != book_id:
            continue
        for j, account in enumerate(book.get("accounts", [])):
            if account["id"] != account_id:
                continue
            account["synced_balance_cents"] = synced_balance_cents
            account["synced_at"] = _now()
            if simplefin_account_id is not None:
                account["simplefin_account_id"] = simplefin_account_id
            book["accounts"][j] = account
            data["books"][i] = book
            _save(store_user, workspace, data)
            return


# ---------------------------------------------------------------------------
# Receipt attachments on transactions (assets attachment pattern)
# ---------------------------------------------------------------------------

RECEIPT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
    "application/pdf": "pdf",
}
MAX_RECEIPT_BYTES = 10 * 1024 * 1024
MAX_RECEIPTS_PER_TX = 10


def _receipts_dir(store_user: str, workspace: str, book_id: str, tx_id: str):
    ws = store_workspace(store_user, workspace)
    return finance_book_dir(store_user, book_id, ws) / "receipts" / tx_id


def _sanitize_filename(name: str) -> str:
    import re as _re

    cleaned = _re.sub(r"[^\w.\- ]", "_", name or "receipt")
    while ".." in cleaned:
        cleaned = cleaned.replace("..", "_")
    return cleaned[:120] or "receipt"


def _update_tx_attachments(
    store_user: str, workspace: str, book_id: str, tx_id: str, attachments: list[dict]
) -> dict | None:
    for year in _shard_years(store_user, workspace, book_id):
        shard = _read_shard(store_user, workspace, book_id, year)
        for i, tx in enumerate(shard.get("transactions", [])):
            if tx["id"] == tx_id:
                tx["attachments"] = attachments
                tx["updated_at"] = _now()
                shard["transactions"][i] = tx
                _write_shard(store_user, workspace, book_id, year, shard)
                return tx
    return None


def add_receipt(
    store_user: str,
    workspace: str,
    book_id: str,
    tx_id: str,
    filename: str,
    mime: str,
    content: bytes,
) -> dict:
    if mime not in RECEIPT_TYPES:
        raise ValueError("Only JPEG/PNG/WebP/AVIF images and PDFs are allowed")
    if len(content) > MAX_RECEIPT_BYTES:
        raise ValueError("Receipt too large (max 10 MB)")
    tx = get_transaction(store_user, workspace, book_id, tx_id)
    if not tx:
        raise ValueError("Transaction not found")
    attachments = list(tx.get("attachments") or [])
    if len(attachments) >= MAX_RECEIPTS_PER_TX:
        raise ValueError(f"Max {MAX_RECEIPTS_PER_TX} receipts per transaction")
    receipt_id = str(uuid.uuid4())
    ext = RECEIPT_TYPES[mime]
    # Disk name is a generated uuid — never derived from user input
    dest = _receipts_dir(store_user, workspace, book_id, tx_id) / f"{receipt_id}.{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    meta = {
        "id": receipt_id,
        "filename": _sanitize_filename(filename),
        "mime": mime,
        "size": len(content),
    }
    attachments.append(meta)
    _update_tx_attachments(store_user, workspace, book_id, tx_id, attachments)
    return meta


def get_receipt(
    store_user: str, workspace: str, book_id: str, tx_id: str, receipt_id: str
) -> tuple | None:
    tx = get_transaction(store_user, workspace, book_id, tx_id)
    if not tx:
        return None
    meta = next((a for a in tx.get("attachments") or [] if a["id"] == receipt_id), None)
    if not meta:
        return None
    ext = RECEIPT_TYPES.get(meta["mime"], "bin")
    path = _receipts_dir(store_user, workspace, book_id, tx_id) / f"{receipt_id}.{ext}"
    if not path.exists():
        return None
    return path, meta["mime"], meta["filename"]


def delete_receipt(
    store_user: str, workspace: str, book_id: str, tx_id: str, receipt_id: str
) -> bool:
    tx = get_transaction(store_user, workspace, book_id, tx_id)
    if not tx:
        return False
    attachments = list(tx.get("attachments") or [])
    meta = next((a for a in attachments if a["id"] == receipt_id), None)
    if not meta:
        return False
    ext = RECEIPT_TYPES.get(meta["mime"], "bin")
    path = _receipts_dir(store_user, workspace, book_id, tx_id) / f"{receipt_id}.{ext}"
    if path.exists():
        path.unlink()
    attachments = [a for a in attachments if a["id"] != receipt_id]
    _update_tx_attachments(store_user, workspace, book_id, tx_id, attachments)
    return True


def next_invoice_number(store_user: str, workspace: str, book_id: str) -> str:
    """Increment the book's invoice sequence and return e.g. INV-2026-0007."""
    data = _load(store_user, workspace)
    for i, book in enumerate(data.get("books", [])):
        if book["id"] != book_id:
            continue
        seq = int(book.get("invoice_seq", 0)) + 1
        book["invoice_seq"] = seq
        prefix = book.get("invoice_prefix", "INV")
        data["books"][i] = book
        _save(store_user, workspace, data)
        year = datetime.now(timezone.utc).year
        return f"{prefix}-{year}-{seq:04d}"
    raise ValueError("Book not found")


def set_deviation_alert_state(
    store_user: str, workspace: str, book_id: str, account_id: str, state: dict
) -> None:
    """Notification-dedup bookkeeping for deviation alerts (not derived data)."""
    data = _load(store_user, workspace)
    for i, book in enumerate(data.get("books", [])):
        if book["id"] != book_id:
            continue
        for j, account in enumerate(book.get("accounts", [])):
            if account["id"] != account_id:
                continue
            account["last_deviation_alert"] = state
            book["accounts"][j] = account
            data["books"][i] = book
            _save(store_user, workspace, data)
            return


# ---------------------------------------------------------------------------
# Payee → category rules (learned from user categorization; applied on import)
# ---------------------------------------------------------------------------

_MAX_RULES = 500


def normalize_payee(payee: str) -> str:
    return " ".join((payee or "").lower().split())


def _rules_file(store_user: str, workspace: str, book_id: str):
    ws = store_workspace(store_user, workspace)
    return finance_rules_path(store_user, book_id, ws)


def list_rules(store_user: str, workspace: str, book_id: str) -> list[dict]:
    return read_json(_rules_file(store_user, workspace, book_id), default={"rules": []}).get(
        "rules", []
    )


def learn_rule(store_user: str, workspace: str, book_id: str, payee: str, category: str) -> None:
    """Upsert a payee→category rule. Called when a user categorizes an imported
    transaction, so the next sync auto-categorizes the same payee."""
    norm = normalize_payee(payee)
    if not norm or not category:
        return
    path = _rules_file(store_user, workspace, book_id)
    data = read_json(path, default={"rules": []})
    rules = data.setdefault("rules", [])
    for rule in rules:
        if rule.get("payee_norm") == norm:
            rule["category"] = category
            rule["count"] = rule.get("count", 0) + 1
            rule["updated_at"] = _now()
            write_json(path, data)
            return
    rules.append(
        {
            "id": str(uuid.uuid4()),
            "payee_norm": norm,
            "category": category,
            "count": 1,
            "updated_at": _now(),
        }
    )
    if len(rules) > _MAX_RULES:
        rules.sort(key=lambda r: r.get("updated_at", ""))
        del rules[: len(rules) - _MAX_RULES]
    write_json(path, data)


def apply_rules(store_user: str, workspace: str, book: dict, payee: str) -> str:
    """Category for a payee if a rule matches AND the category still exists."""
    norm = normalize_payee(payee)
    if not norm:
        return ""
    valid = {c["name"] for c in book.get("categories", [])}
    for rule in list_rules(store_user, workspace, book["id"]):
        if rule.get("payee_norm") == norm and rule.get("category") in valid:
            return rule["category"]
    return ""


def delete_rule(store_user: str, workspace: str, book_id: str, rule_id: str) -> bool:
    path = _rules_file(store_user, workspace, book_id)
    data = read_json(path, default={"rules": []})
    rules = data.get("rules", [])
    remaining = [r for r in rules if r.get("id") != rule_id]
    if len(remaining) == len(rules):
        return False
    data["rules"] = remaining
    write_json(path, data)
    return True


# ---------------------------------------------------------------------------
# Sharing mutations (Phase E) — entries live on the OWNER's book/account
# ---------------------------------------------------------------------------


def resolve_target_users(target: str) -> list[str]:
    """Concrete user names for a share target. Raises ValueError on unknowns."""
    from services import auth_service

    users = auth_service.list_users()
    names = [u["name"] for u in users]
    if target == "household":
        return names
    if target == "team":
        return [u["name"] for u in users if "business" in (u.get("workspaces") or ["personal"])]
    if target.startswith("role:"):
        role = target[5:]
        from services.features_service import load_features

        if role not in (load_features().get("roles") or {}):
            raise ValueError(f"Unknown role: {role!r}")
        return [u["name"] for u in users if u.get("feature_role", "member") == role]
    if target in names:
        return [target]
    raise ValueError(f"Unknown share target: {target!r}")


def _clean_share_entries(entries: list[dict], existing: list[dict], pool: bool) -> list[dict]:
    """Validate share/contributor entries; preserve accepted[] across re-shares."""
    old_accepted = {e.get("target"): e.get("accepted") for e in (existing or [])}
    cleaned = []
    seen = set()
    for entry in entries or []:
        target = (entry.get("target") or "").strip()
        if not target or target in seen:
            continue
        seen.add(target)
        resolve_target_users(target)  # validates
        access = entry.get("access", "read")
        if access not in ACCESS_LEVELS:
            raise ValueError(f"Invalid access level: {access!r}")
        out = {"target": target, "access": access}
        if access == "contribute":
            out["caps"] = normalize_caps(entry.get("caps"))
        if not pool:
            # Personal shares use the accept handshake; keep prior acceptances
            prior = old_accepted.get(target)
            out["accepted"] = prior if isinstance(prior, list) else []
        cleaned.append(out)
    return cleaned


def _clean_hidden(hidden: list) -> list[str]:
    out = []
    for token in hidden or []:
        token = (token or "").strip()
        if not token:
            continue
        if token.startswith("role:"):
            from services.features_service import load_features

            if token[5:] not in (load_features().get("roles") or {}):
                raise ValueError(f"Unknown role: {token[5:]!r}")
        else:
            resolve_target_users(token)  # must be a real user name
        out.append(token)
    return out


def update_access(
    store_user: str,
    workspace: str,
    book_id: str,
    shared_with: list[dict] | None = None,
    hidden_from: list | None = None,
    contributors: list[dict] | None = None,
    account_id: str | None = None,
) -> tuple[dict, list[str]]:
    """Replace the audience on a book (or one account when account_id is set).

    Pool books take `contributors` (no handshake) and never `shared_with`;
    personal books the reverse. Returns (record, users_to_notify) where
    users_to_notify are newly-targeted users who have not accepted yet."""
    pool = is_pool(store_user)
    if pool and shared_with is not None:
        raise ValueError("Pool books are workspace-visible — use contributors, not shares")
    if not pool and contributors is not None:
        raise ValueError("Contributors are for pool books — use shared_with")

    data = _load(store_user, workspace)
    for i, book in enumerate(data.get("books", [])):
        if book["id"] != book_id:
            continue
        target_record = book
        if account_id:
            target_record = next(
                (a for a in book.get("accounts", []) if a["id"] == account_id), None
            )
            if target_record is None:
                raise ValueError("Account not found")

        to_notify: list[str] = []
        if shared_with is not None:
            cleaned = _clean_share_entries(
                shared_with, target_record.get("shared_with"), pool=False
            )
            target_record["shared_with"] = cleaned
            for entry in cleaned:
                accepted = set(entry.get("accepted") or [])
                for name in resolve_target_users(entry["target"]):
                    if name != store_user and name not in accepted:
                        to_notify.append(name)
        if contributors is not None:
            target_record["contributors"] = _clean_share_entries(
                contributors, target_record.get("contributors"), pool=True
            )
        if hidden_from is not None and not account_id:
            book["hidden_from"] = _clean_hidden(hidden_from)

        book["updated_at"] = _now()
        data["books"][i] = book
        _save(store_user, workspace, data)

        if not pool:
            from services.finance_index import reindex_owner

            reindex_owner(store_user)
        return (target_record, sorted(set(to_notify)))
    raise ValueError("Book not found")


def _walk_share_entries(book: dict):
    """Yield every shared_with entry list on a book (book-level + accounts)."""
    yield book, book.setdefault("shared_with", [])
    for account in book.get("accounts", []):
        yield account, account.setdefault("shared_with", [])


def respond_share(viewer: str, owner: str, workspace: str, book_id: str, accept: bool) -> bool:
    """Accept adds the viewer to accepted[] on every entry targeting them
    (book + account levels). Decline/leave removes a by-name entry entirely
    and drops the viewer from group-entry acceptance (silent, like assets)."""
    data = _load(owner, workspace)
    changed = False
    for i, book in enumerate(data.get("books", [])):
        if book["id"] != book_id:
            continue
        for _record, entries in _walk_share_entries(book):
            kept = []
            for entry in entries:
                targets_viewer = False
                try:
                    targets_viewer = viewer in resolve_target_users(entry.get("target", ""))
                except ValueError:
                    pass
                if not targets_viewer:
                    kept.append(entry)
                    continue
                if accept:
                    accepted = entry.setdefault("accepted", [])
                    if viewer not in accepted:
                        accepted.append(viewer)
                        changed = True
                    kept.append(entry)
                else:
                    if entry.get("target") == viewer:
                        changed = True  # drop the by-name entry entirely
                        continue
                    accepted = entry.get("accepted")
                    if isinstance(accepted, list) and viewer in accepted:
                        entry["accepted"] = [n for n in accepted if n != viewer]
                        changed = True
                    kept.append(entry)
            entries[:] = kept
        book["updated_at"] = _now()
        data["books"][i] = book
        break
    else:
        return False
    if changed:
        _save(owner, workspace, data)
        from services.finance_index import reindex_owner

        reindex_owner(owner)
    return changed
