"""Home Health block — lease/mortgage countdown, open/overdue task counts,
upcoming event count, and this month's tagged finance activity for one
home. Reads task_service/events_service/finance_service directly off
find_home()'s already-resolved (store_user, store_workspace) — never
search_service.search(), matching every other converted module's own
dashboard_block.py resolver (assets', calendar's, finance's own
resolve_finance_activity), none of which route through search: BlockRenderCtx
doesn't carry a full current_user dict the way search() requires, and the
raw service records already carry due_date/status/amount_cents/date, which
the lightweight search-provider shape deliberately drops. A pool home's
tasks/events already live under the exact same task_service/events_service
call just pointed at the pool pseudo-user, so one call per module covers
both personal and pool homes — no household/team-specific lookup needed
here, unlike the generic cross-module /homes/{id}/items endpoint."""

from calendar import monthrange
from datetime import date

from module_packages.homes.backend import service as homes_service
from services import events_service, finance_service, task_service
from services.auth_service import today_for_user
from services.dashboard_blocks.registry import (
    BlockRenderCtx,
    BlockRenderResult,
    BlockSpec,
    register,
)


def _tagged(records: list[dict], tag: str) -> list[dict]:
    tag_l = tag.lower()
    return [r for r in records if tag_l in {t.lower() for t in (r.get("tags") or [])}]


def _amount_due_this_month(ctx: BlockRenderCtx, tag: str) -> int | None:
    """Sums this month's tagged, negative (expense) transaction amounts
    across every book the viewer can see — wrapped separately from the
    rest of the resolver so a Finance hiccup only blanks this one figure,
    not the lease/task/event stats that DID resolve (same per-branch
    degrade resolve_finance_activity's own contact_id path already uses)."""
    try:
        today = date.today()
        month_start = today.replace(day=1).isoformat()
        month_end = today.replace(day=monthrange(today.year, today.month)[1]).isoformat()
        total = 0
        for book in finance_service.list_visible_books(
            ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace
        ):
            store_user = finance_service.store_for_annotated(book, ctx.viewer, ctx.workspace)
            txs, _total = finance_service.list_transactions(
                store_user,
                ctx.workspace,
                book["id"],
                date_from=month_start,
                date_to=month_end,
                limit=1000,
            )
            for tx in _tagged(txs, tag):
                if tx.get("amount_cents", 0) < 0:
                    total += -tx["amount_cents"]
        return total
    except Exception:
        return None


def resolve_home_health(ctx: BlockRenderCtx) -> BlockRenderResult:
    home_id = ctx.config.get("home_id")
    if not home_id:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    found = homes_service.find_home(ctx.viewer, ctx.workspace, home_id)
    if found is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    store_user, store_workspace, home = found
    tag = home["tag"]
    today_iso = today_for_user(store_user).isoformat()

    tasks = _tagged(task_service.list_tasks(store_user, store_workspace), tag)
    open_tasks = [t for t in tasks if t.get("status") == "pending"]
    overdue_tasks = [t for t in open_tasks if t.get("due_date") and t["due_date"] < today_iso]

    events = _tagged(events_service.list_events(store_user, store_workspace), tag)
    upcoming_events = [
        e for e in events if (e.get("end_date") or e.get("start_date") or "") >= today_iso
    ]

    variant = home.get(home["ownership_type"]) or {}
    return BlockRenderResult(
        ok=True,
        data={
            "home_name": home["name"],
            "ownership_type": home["ownership_type"],
            "lease_end": variant.get("lease_end"),
            "purchase_date": variant.get("purchase_date"),
            "open_task_count": len(open_tasks),
            "overdue_task_count": len(overdue_tasks),
            "upcoming_event_count": len(upcoming_events),
            "amount_due_cents": _amount_due_this_month(ctx, tag),
        },
    )


register(
    BlockSpec(
        type="home_health",
        label="Home Health",
        category="record_linked",
        resolver=resolve_home_health,
        record_ref_fields={"home_id": "homes"},
        module="homes",
    )
)
