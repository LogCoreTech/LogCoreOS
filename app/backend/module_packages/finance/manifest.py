"""Finance module manifest. See module_registry.py for the ModuleManifest
contract and docs/MEMORY.md's 2026-08-28 entry for the full design.

The last and largest of the three biggest remaining modules (Assets,
Contacts, Finance, deliberately last per the rollout plan) — and the only
one structurally split across SIX separate router files rather than one:
`routers/finance.py` (books/accounts/transactions/reports/net worth),
`finance_banking.py` (SimpleFIN bank sync, admin-managed), `finance_planning.py`
(budgets/recurring/planned/projection), `finance_invoicing.py` (clients/
invoices/payments/AR), `finance_sharing.py` (access grants), and
`finance_transfers.py` (cross-book/cross-workspace transfers). All six
moved into this package's own backend/ directory as router.py/
router_banking.py/router_planning.py/router_invoicing.py/router_sharing.py/
router_transfers.py — `ModuleManifest.get_router()` only supports returning
ONE router, so `_get_router()` below composes all six into a single parent
router via nested `include_router()` calls, each keeping its OWN original
tag (no new umbrella "finance" tag added) so the OpenAPI grouping stays
byte-identical to before this conversion, not just functionally equivalent.
The 4 sibling routers that used to import shared helpers (`_find_or_404`/
`_require_edit`/`_require_full_read`/`_validate_id`) directly from
`routers.finance` now import them from `module_packages.finance.backend.router`
instead — a pure import-path fix, the helpers themselves are unchanged.

services/finance_service.py, services/finance_invoice_service.py, and
services/finance_index.py all deliberately stay core, never moving into
this package — the strongest "stays core" case of any conversion yet,
stronger even than assets_service.py's/contacts_service.py's own:
module_packages/contacts/backend/router.py's `GET /contacts/{id}/finance`
endpoint makes deep, real, MULTIPLE-function calls into both
(`list_visible_books`/`store_for_annotated`/`list_transactions`/
`list_transactions_for_asset` and `list_clients`/`list_invoices`/
`list_invoices_for_deal`) — that endpoint already has its own defensive
`if "finance" in disabled_modules: return {"available": False}` check,
meaning Contacts' own conversion had already anticipated Finance staying
core. On top of that: services/user_deletion_service.py imports both
directly; services/dashboard_blocks/_actions.py imports finance_service
for its nav_button resolver; main.py's _warm_share_index() unconditionally
rebuilds finance_index at every boot, same as assets/contacts/notes.

services/finance_planning_service.py and services/simplefin_service.py
ALSO stay core — a genuinely different reason than the above, and the
first time this exact shape has come up: neither has a sibling-module or
core-router dependent, but BOTH are imported directly by scheduler.py's
own job functions (job_finance_nightly, job_simplefin_sync), registered
unconditionally at boot regardless of any module's install state. This
mirrors n8n_service.py's own precedent from Automations' conversion
(docs/MEMORY.md, 2026-08-25: "n8n_service.py (scheduler.py's boot/cron
jobs... import it directly)" stayed core for the identical reason) rather
than being a new call — a scheduler dependency is treated exactly like a
sibling-module dependency for this decision, not a weaker signal. One
small, genuinely new wrinkle: finance_planning_service.py's own
`budget_status()` needed `month_end()`, previously defined in
finance_reports.py (which DOES move, see below, having zero core
consumers of its own). Duplicating a two-line pure calendar helper was
judged better than forcing a core file's own correctness to depend on an
optional module's package, so `month_end()` now lives IN
finance_planning_service.py, and the moved reports.py imports it back
from there instead of the reverse.

services/finance_reports.py and services/finance_import_service.py DO
move into this package (as reports.py and import_service.py) — confirmed
by direct grep to have zero consumers outside Finance's own routers/
services (reports.py's sole non-Finance-owned caller, finance_planning_service.py,
only ever needed month_end(), resolved above; nothing calls
finance_import_service directly except finance_banking.py's CSV endpoints
and its own tests). Matches automations' own `inbox_service.py` precedent
— a module-exclusive helper with no external dependents moves freely.

services/dashboard_blocks/_finance.py moved into this package's own
dashboard_block.py (finance_activity, finance_book_report), both gaining
module="finance" gating for the first time — confirmed genuinely
Finance-owned (unlike Contacts' custom_fields, neither resolver branches
to another module's service), a clean move exactly like every prior
conversion's own exclusively-owned blocks.

13 admin-lifecycle SimpleFIN endpoints inside finance_banking.py
(GET/POST/DELETE /simplefin/connections, /pool-summary, /claim, /reveal,
/{user_id}, /sync, and the 7 /simplefin/pool/{pool}/* routes) were found
gated by require_admin ALONE, never require_module("finance") — the same
narrow inconsistency Contacts' own PUT /contacts/fields had (an admin
whose own account has Finance disabled could still manage every user's
bank connections), not Assets' own "another module depends on this"
shape. Fixed by adding require_module("finance") alongside require_admin
on all 13, matching Contacts' own fix exactly. Every other finance_banking.py
endpoint (member-facing SimpleFIN actions, CSV import, payee rules) was
already correctly gated on require_module.

No markdown Brain content exists for Finance at all (books.json, per-book
per-year transaction shards, and receipt attachments under
Finance/books/{id}/receipts/ are all JSON/binary) — same structural
category as Tasks/Dashboards/Assets/Contacts, not Notes/Chat's
conditional owned_brain_paths gap. "Finance" added to the unconditional
structural skip sets (routers/brain.py's _ALWAYS_SKIP, agent_service.py's
_brain_skip()) for documentation honesty, matching every prior JSON-only
module's own precedent.

The 9 AI agent tools (list_finance_books/list_finance_transactions/
get_finance_report/get_budget_status/get_balance_projection/create_invoice/
add_finance_transaction/categorize_transaction/mark_invoice_paid) lived
unfiltered in agent_service.py's static _USER_TOOLS list before this — the
sixth confirmed instance of the same enforcement gap every prior
conversion found and closed in its turn. No admin-only Finance tool
exists, so this manifest declares no admin_agent_tools."""

from pathlib import Path

from module_registry import ModuleManifest, MetricProviderSpec


def _resolve_budget_pct(config: dict, user: dict, workspace: str) -> dict:
    """Goals metric provider (2026-08-28) — a budget category's spent/limit
    percent, reusing finance_planning_service.budget_status()'s own
    spent*100/limit computation directly rather than re-deriving it. Looks
    the book up through the same visibility rules any other Finance read
    uses; defaults to a plain member view when the caller (e.g. a pool
    goal, or a dashboard-block context with no real role) doesn't carry
    role/is_admin — the safe minimum-privilege default, never
    over-granting. Never raises — module_registry.MetricProviderSpec's own
    contract requires this to degrade to 0% on any lookup failure, not
    crash the goal that's using it."""
    from datetime import date

    from services import finance_service
    from services.finance_planning_service import budget_status

    book_id = config.get("book_id")
    category = config.get("category")
    if not book_id or not category:
        return {"current": 0, "target": None, "pct": 0}

    viewer = user.get("name", "")
    viewer_role = user.get("role", "member")
    is_admin = user.get("role") == "admin"
    books = finance_service.list_visible_books(viewer, viewer_role, is_admin, workspace)
    book = next((b for b in books if b["id"] == book_id), None)
    if book is None:
        return {"current": 0, "target": None, "pct": 0}

    month = date.today().isoformat()[:7]
    for status in budget_status(book.get("_owner", viewer), workspace, book, month):
        if status["category"] == category:
            return {
                "current": status["spent_cents"] / 100,
                "target": status["monthly_limit_cents"] / 100,
                "pct": status["pct"],
            }
    return {"current": 0, "target": None, "pct": 0}


def _get_router():
    from fastapi import APIRouter

    from module_packages.finance.backend import router as _core
    from module_packages.finance.backend import router_banking as _banking
    from module_packages.finance.backend import router_invoicing as _invoicing
    from module_packages.finance.backend import router_planning as _planning
    from module_packages.finance.backend import router_sharing as _sharing
    from module_packages.finance.backend import router_transfers as _transfers

    combined = APIRouter()
    combined.include_router(_core.router, tags=["finance"])
    combined.include_router(_banking.router, tags=["finance-banking"])
    combined.include_router(_planning.router, tags=["finance-planning"])
    combined.include_router(_invoicing.router, tags=["finance-invoicing"])
    combined.include_router(_sharing.router, tags=["finance-sharing"])
    combined.include_router(_transfers.router, tags=["finance-transfers"])
    return combined


def m030_backfill_finance_installed_from_existing_data(brain: Path) -> None:
    """Every instance that existed before this migration shipped had finance
    permanently on — mark it installed so upgrading never silently takes
    the feature away. A genuinely fresh instance has no `_system/features.json`
    yet, so it correctly skips this and starts with finance NOT installed.
    Same existence-guard idiom as journal's m015/calendar's m020/notes' m026/
    assets' m028/contacts' m029."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return

    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return

    mod_store_service.mark_installed("finance", by="migration:m030")


MODULE = ModuleManifest(
    id="finance",
    display_name="Finance",
    description="Personal and business finances: books, accounts, transactions, bank sync, budgets, and invoicing.",
    icon="💵",  # matches constants.js's existing nav icon; help_section below keeps its own pre-existing 💰, unrelated/unchanged
    version="1.0.0",
    router_prefix="/api/v1/finance",
    router_tags=[],
    get_router=_get_router,
    owned_brain_paths=["Finance"],
    owned_agent_tools=[
        "list_finance_books",
        "list_finance_transactions",
        "get_finance_report",
        "get_budget_status",
        "get_balance_projection",
        "create_invoice",
        "add_finance_transaction",
        "categorize_transaction",
        "mark_invoice_paid",
    ],
    read_only_agent_tools=[
        "list_finance_books",
        "list_finance_transactions",
        "get_finance_report",
        "get_budget_status",
        "get_balance_projection",
    ],
    owned_block_types=["finance_activity", "finance_book_report"],
    owned_metric_providers=[
        MetricProviderSpec(
            key="budget_pct",
            label="Finance: Budget Category %",
            config_schema=[
                {"key": "book_id", "label": "Finance Book", "kind": "financeBook"},
                {"key": "category", "label": "Budget Category", "kind": "text"},
            ],
            resolve=_resolve_budget_pct,
        ),
    ],
    migrations=[
        (
            "finance:m030_backfill_finance_installed_from_existing_data",
            m030_backfill_finance_installed_from_existing_data,
        ),
    ],
    help_section={
        "id": "finance",
        "icon": "💰",
        "title": "Finance",
        "blurb": "Personal and business finances: books with accounts and transactions, bank sync, budgets, recurring bills, invoicing, and sharing with tight controls.",
        "howto": [
            "Create a Book, then add accounts (checking, savings, credit, cash) and customize its categories.",
            "Add transactions by hand, import a CSV, or have an admin connect your bank via SimpleFIN (read-only).",
            "Moving money between two of your own books (even across personal and business)? Use Transfer instead of Expense/Income — pick the destination book and account and both sides are created and linked automatically, and never show up as income or expense in your reports or budgets.",
            "Set budgets and recurring bills to get alerts and a projected balance; deviations from your bank balance flag early.",
            "Invoice clients, record partial payments, and see who's behind under Invoices → AR.",
            "Share a book or a single account with someone — \"contribute\" access can be limited to submitting expenses with no visibility into balances.",
        ],
        "tips": [
            "Your personal books are private — even admins can't see them unless you share them.",
            "Everything derived (balances, reports, AR) is computed live; you never have to reconcile stored totals.",
        ],
        "modules": ["finance"],
    },
)
