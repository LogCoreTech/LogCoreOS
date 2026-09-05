"""Today-at-a-glance dashboard block (item #30, 2026-09-04 UX Polish
Batch) — a small "3/7 done today" stat, distinct from the This Week digest
(services/suggestions_service.py) and the weekly summary strip. Gated on
`module="dashboard"` (not owned by any single data module — it reads Tasks
data the same way `ai_usage_me` above reads AI usage data without being
Chat-owned) rather than left ungated the way `pool_tasks` was before
Household/Team's own conversion caught that exact gap."""

from services.dashboard_blocks.registry import (
    BlockRenderCtx,
    BlockRenderResult,
    BlockSpec,
    register,
    scoped_target,
)


def resolve_today_glance(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")

    from services.auth_service import today_for_user
    from services.task_service import list_tasks

    today = today_for_user(target).isoformat()
    due_today = [t for t in list_tasks(target, ctx.workspace) if t.get("due_date") == today]
    done_today = [t for t in due_today if t.get("status") == "done"]
    return BlockRenderResult(ok=True, data={"done": len(done_today), "total": len(due_today)})


register(
    BlockSpec(
        type="today_glance",
        label="Today at a Glance",
        category="live_aggregate",
        resolver=resolve_today_glance,
        scope_configurable=True,
        module="dashboard",
    )
)
