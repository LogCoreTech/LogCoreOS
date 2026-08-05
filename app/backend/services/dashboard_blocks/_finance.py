"""Finance blocks — Finance Activity (asset/contact/book variants) and Finance
Book Report. Every resolver goes through finance_service.find_book /
list_transactions_for_asset, the SAME access gate the Finance router itself
uses — a viewer who can't see a book independently gets locked here too."""

from services import finance_reports, finance_service
from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register


def resolve_finance_activity(ctx: BlockRenderCtx) -> BlockRenderResult:
    asset_id = ctx.config.get("asset_id")
    contact_id = ctx.config.get("contact_id")
    book_id = ctx.config.get("book_id")

    if asset_id:
        try:
            txs = finance_service.list_transactions_for_asset(
                ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, asset_id
            )
        except Exception:
            return BlockRenderResult(ok=False, locked_reason="no_access")
        return BlockRenderResult(ok=True, data={"transactions": txs[:10]})

    if book_id:
        found = finance_service.find_book(ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, book_id)
        if found is None:
            return BlockRenderResult(ok=False, locked_reason="no_access")
        store_user, book, access = found
        txs, _total = finance_service.list_transactions(store_user, ctx.workspace, book_id, limit=10)
        return BlockRenderResult(ok=True, data={"transactions": txs, "book_name": book.get("name")})

    if contact_id:
        # Lightweight payee-transaction view, scoped to the viewer's own finance
        # access (mirrors the read side of GET /contacts/{id}/finance without
        # duplicating its full Job-P&L computation for a dashboard-sized block).
        results = []
        try:
            for book in finance_service.list_visible_books(
                ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace
            ):
                store_user = finance_service.store_for_annotated(book, ctx.viewer, ctx.workspace)
                txs, _total = finance_service.list_transactions(store_user, ctx.workspace, book["id"], limit=200)
                results.extend(t for t in txs if t.get("payee_contact_id") == contact_id)
        except Exception:
            return BlockRenderResult(ok=False, locked_reason="no_access")
        results.sort(key=lambda t: t.get("date", ""), reverse=True)
        return BlockRenderResult(ok=True, data={"transactions": results[:10]})

    return BlockRenderResult(ok=False, locked_reason="not_found")


def resolve_finance_book_report(ctx: BlockRenderCtx) -> BlockRenderResult:
    book_id = ctx.config.get("book_id")
    if not book_id:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    found = finance_service.find_book(ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, book_id)
    if found is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    store_user, book, access = found
    from datetime import date

    month = ctx.config.get("month") or date.today().strftime("%Y-%m")
    report = finance_reports.monthly_report(store_user, ctx.workspace, book, month)
    return BlockRenderResult(ok=True, data={"report": report, "book_name": book.get("name")})


register(
    BlockSpec(
        type="finance_activity",
        label="Finance Activity",
        category="record_linked",
        resolver=resolve_finance_activity,
        record_ref_fields={"asset_id": "assets", "contact_id": "contacts", "book_id": "finance_books"},
    )
)
register(
    BlockSpec(
        type="finance_book_report",
        label="Finance Book Report",
        category="record_linked",
        resolver=resolve_finance_book_report,
        record_ref_fields={"book_id": "finance_books"},
    )
)
