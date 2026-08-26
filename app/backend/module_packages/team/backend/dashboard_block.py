"""Team's own dashboard block — the business-workspace half of the old
shared `pool_tasks` block, split apart when household/team converted
(2026-08-25). See household/backend/dashboard_block.py for the full
reasoning (BlockSpec.module can only hold one string) and
household/manifest.py's m023 migration for the block-type-rename
carry-forward this pairs with."""

from services import task_service
from services.dashboard_blocks.registry import (
    BlockRenderCtx,
    BlockRenderResult,
    BlockSpec,
    register,
)


def resolve_team_tasks(ctx: BlockRenderCtx) -> BlockRenderResult:
    if ctx.workspace != "business":
        return BlockRenderResult(ok=False, locked_reason="not_found")
    all_tasks = task_service.list_tasks("_team", "personal")
    pending = [t for t in all_tasks if t.get("status") == "pending"][:5]
    return BlockRenderResult(ok=True, data={"tasks": pending})


register(
    BlockSpec(
        type="team_tasks",
        label="Team Pool Tasks",
        category="live_aggregate",
        resolver=resolve_team_tasks,
        workspace="business",
        module="team",
    )
)
