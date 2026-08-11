"""Journal Entry block — journal is personal (never shared), so this only ever
resolves via the owner/viewer scope mechanic, same as Tasks."""

from services import journal_service
from services.dashboard_blocks._tasks import _scoped_target
from services.dashboard_blocks.registry import (
    BlockRenderCtx,
    BlockRenderResult,
    BlockSpec,
    register,
)


def resolve_journal_entry(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    entry_date = ctx.config.get("date")
    if target is None or not entry_date:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    entry = journal_service.get_entry(target, entry_date, ctx.workspace)
    if entry is None:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    content = entry.get("content", "")
    return BlockRenderResult(ok=True, data={"date": entry_date, "preview": content[:400]})


register(
    BlockSpec(
        type="journal_entry",
        label="Journal Entry",
        category="record_linked",
        resolver=resolve_journal_entry,
        scope_configurable=True,
        record_ref_fields={"date": "journal"},
    )
)
