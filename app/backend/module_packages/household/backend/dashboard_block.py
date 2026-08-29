"""Household's own dashboard block — the personal-workspace half of the old
shared `pool_tasks` block, split apart when household/team converted
(2026-08-25). `BlockSpec.module` can only ever hold one string, so a single
block type serving both pools couldn't be gated to either module
individually — see team/backend/dashboard_block.py for the business-
workspace half, and household/manifest.py's m023 migration for the
block-type-rename carry-forward (any dashboard that already had a
`pool_tasks` block needs it rewritten to `household_tasks`/`team_tasks`
based on that dashboard's own workspace, or the block becomes
unresolvable the moment this code deploys).

household_goals (2026-08-28, added when Goals converted) follows the exact
same module="household" precedent, not module="goals" — gated on POOL
membership, same as household_tasks. Uninstalling Household hides this
block regardless of Goals' own state; the resolver itself still needs
Goals to be installed to have any data, handled the same way any other
disabled-module read degrades (an empty/error result, not a crash)."""

from module_packages.goals.backend import service as goals_service
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


def resolve_household_goals(ctx: BlockRenderCtx) -> BlockRenderResult:
    if ctx.workspace != "personal":
        return BlockRenderResult(ok=False, locked_reason="not_found")
    user = {"name": "_household"}
    roots = goals_service.get_root_goals("_household", "personal")
    goals = [
        {**g, "progress": goals_service.compute_progress("_household", g, "personal", user)}
        for g in roots
    ]
    return BlockRenderResult(ok=True, data={"goals": goals})


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
register(
    BlockSpec(
        type="household_goals",
        label="Household Pool Goals",
        category="live_aggregate",
        resolver=resolve_household_goals,
        workspace="personal",
        module="household",
    )
)
