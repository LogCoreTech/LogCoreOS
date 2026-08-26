"""Household's own dashboard block — the personal-workspace half of the old
shared `pool_tasks` block, split apart when household/team converted
(2026-08-25). `BlockSpec.module` can only ever hold one string, so a single
block type serving both pools couldn't be gated to either module
individually — see team/backend/dashboard_block.py for the business-
workspace half, and household/manifest.py's m023 migration for the
block-type-rename carry-forward (any dashboard that already had a
`pool_tasks` block needs it rewritten to `household_tasks`/`team_tasks`
based on that dashboard's own workspace, or the block becomes
unresolvable the moment this code deploys)."""

from services import task_service
from services.dashboard_blocks.registry import (
    BlockRenderCtx,
    BlockRenderResult,
    BlockSpec,
    register,
)


def resolve_household_tasks(ctx: BlockRenderCtx) -> BlockRenderResult:
    if ctx.workspace != "personal":
        return BlockRenderResult(ok=False, locked_reason="not_found")
    all_tasks = task_service.list_tasks("_household", "personal")
    pending = [t for t in all_tasks if t.get("status") == "pending"][:5]
    return BlockRenderResult(ok=True, data={"tasks": pending})


register(
    BlockSpec(
        type="household_tasks",
        label="Household Pool Tasks",
        category="live_aggregate",
        resolver=resolve_household_tasks,
        workspace="personal",
        module="household",
    )
)
