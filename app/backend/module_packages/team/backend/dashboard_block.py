"""Team's own dashboard block — the business-workspace half of the old
shared `pool_tasks` block, split apart when household/team converted
(2026-08-25). See household/backend/dashboard_block.py for the full
reasoning (BlockSpec.module can only hold one string) and
household/manifest.py's m023 migration for the block-type-rename
carry-forward this pairs with.

team_goals (2026-08-28, added when Goals converted) follows the same
module="team" precedent as team_tasks, not module="goals" — see
household/backend/dashboard_block.py's own household_goals docstring for
the full reasoning, identical here."""

from module_packages.goals.backend import service as goals_service
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


def resolve_team_goals(ctx: BlockRenderCtx) -> BlockRenderResult:
    if ctx.workspace != "business":
        return BlockRenderResult(ok=False, locked_reason="not_found")
    # _team's own storage always lives at workspace="personal" — see
    # goals/backend/router.py's module docstring for why.
    user = {"name": "_team"}
    roots = goals_service.get_root_goals("_team", "personal")
    goals = [
        {**g, "progress": goals_service.compute_progress("_team", g, "personal", user)}
        for g in roots
    ]
    return BlockRenderResult(ok=True, data={"goals": goals})


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
register(
    BlockSpec(
        type="team_goals",
        label="Team Pool Goals",
        category="live_aggregate",
        resolver=resolve_team_goals,
        workspace="business",
        module="team",
    )
)
