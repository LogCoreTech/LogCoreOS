"""Tasks/Goals blocks — pure reuse of priority_service/task_service."""

from services import priority_service, task_service
from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register


def _scoped_target(ctx: BlockRenderCtx) -> str | None:
    """scope='owner' blocks only ever succeed when ctx.viewer IS that target —
    i.e. on Pass 2 (owner identity) or when the viewer happens to be the owner.
    scope='viewer' (default) always targets the caller themselves."""
    target = ctx.dashboard_owner if ctx.config.get("scope") == "owner" else ctx.viewer
    return target if ctx.viewer == target else None


def resolve_top3(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    tasks = priority_service.get_top3(target, ctx.workspace)
    return BlockRenderResult(ok=True, data={"tasks": tasks})


def resolve_due_today(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    from services.auth_service import today_for_user

    today_str = today_for_user(target).isoformat()
    all_tasks = task_service.list_tasks(target, ctx.workspace)
    due = [
        t
        for t in all_tasks
        if t.get("status") == "pending" and t.get("due_date") == today_str and t.get("type") != "goal"
    ]
    return BlockRenderResult(ok=True, data={"tasks": due})


def resolve_streaks(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    all_tasks = task_service.list_tasks(target, ctx.workspace)
    streaks = sorted(
        [t for t in all_tasks if t.get("type") == "recurring" and (t.get("streak_count") or 0) > 0],
        key=lambda t: t.get("streak_count", 0),
        reverse=True,
    )[:5]
    return BlockRenderResult(ok=True, data={"tasks": streaks})


def resolve_goals_progress(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    all_tasks = task_service.list_tasks(target, ctx.workspace)
    goals = [t for t in all_tasks if t.get("type") == "goal"]
    return BlockRenderResult(ok=True, data={"goals": goals})


def resolve_single_task(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    task_id = ctx.config.get("task_id")
    if target is None or not task_id:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    task = task_service.get_task(target, task_id, ctx.workspace)
    if task is None:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    return BlockRenderResult(ok=True, data={"task": task})


register(
    BlockSpec(
        type="top3_tasks",
        label="Top 3 Tasks",
        category="live_aggregate",
        resolver=resolve_top3,
        scope_configurable=True,
    )
)
register(
    BlockSpec(
        type="due_today",
        label="Due Today",
        category="live_aggregate",
        resolver=resolve_due_today,
        scope_configurable=True,
    )
)
register(
    BlockSpec(
        type="streaks",
        label="Active Streaks",
        category="live_aggregate",
        resolver=resolve_streaks,
        scope_configurable=True,
    )
)
register(
    BlockSpec(
        type="goals_progress",
        label="Goals Progress",
        category="live_aggregate",
        resolver=resolve_goals_progress,
        scope_configurable=True,
    )
)
register(
    BlockSpec(
        type="single_task",
        label="Single Task",
        category="record_linked",
        resolver=resolve_single_task,
        scope_configurable=True,
        record_ref_fields={"task_id": "tasks"},
    )
)
