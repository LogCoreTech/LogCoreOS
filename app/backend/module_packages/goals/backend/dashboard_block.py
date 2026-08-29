"""Goals' own dashboard block — the personal-workspace goals_progress block,
rebuilt here from the old tasks-owned version (which just listed type=="goal"
Task rows with no real progress). Now shows each root-level goal with its
actual computed percent. Pool variants (household_goals/team_goals) live in
household's/team's own dashboard_block.py, mirroring exactly how
household_tasks/team_tasks already split the old pool_tasks block — a
BlockSpec.module can only ever hold one string, and gating on the POOL
module (not "goals") is the established precedent those two set."""

from module_packages.goals.backend import service as goals_service
from services.dashboard_blocks.registry import (
    BlockRenderCtx,
    BlockRenderResult,
    BlockSpec,
    register,
    scoped_target,
)


def resolve_goals_progress(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    roots = goals_service.get_root_goals(target, ctx.workspace)
    user = {"name": target}
    goals = [
        {**g, "progress": goals_service.compute_progress(target, g, ctx.workspace, user)}
        for g in roots
    ]
    return BlockRenderResult(ok=True, data={"goals": goals})


register(
    BlockSpec(
        type="goals_progress",
        label="Goals Progress",
        category="live_aggregate",
        resolver=resolve_goals_progress,
        scope_configurable=True,
        module="goals",
    )
)
