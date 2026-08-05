"""Calendar blocks — Upcoming Events (live-aggregate) and Single Event
(record-linked). Reuses events_service as-is; date filtering done in-process,
no new endpoint needed."""

from datetime import date

from services import events_service
from services.dashboard_blocks._tasks import _scoped_target
from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register


def resolve_upcoming_events(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    today = date.today().isoformat()
    events = [e for e in events_service.list_events(target, ctx.workspace) if e.get("date", "") >= today]
    events.sort(key=lambda e: e.get("date", ""))
    return BlockRenderResult(ok=True, data={"events": events[:5]})


def resolve_single_event(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    event_id = ctx.config.get("event_id")
    if target is None or not event_id:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    event = events_service.get_event(target, event_id, ctx.workspace)
    if event is None:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    return BlockRenderResult(ok=True, data={"event": event})


register(
    BlockSpec(
        type="upcoming_events",
        label="Upcoming Events",
        category="live_aggregate",
        resolver=resolve_upcoming_events,
        scope_configurable=True,
    )
)
register(
    BlockSpec(
        type="single_event",
        label="Single Event",
        category="record_linked",
        resolver=resolve_single_event,
        scope_configurable=True,
        record_ref_fields={"event_id": "calendar"},
    )
)
