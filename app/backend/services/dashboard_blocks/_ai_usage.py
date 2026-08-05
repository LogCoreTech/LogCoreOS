"""AI Usage / Chat blocks. `ai_usage_overview` is admin-only — its data spans
every user on the instance, so the registry's admin_only flag hides it from
the picker for non-admins and this resolver ALSO independently checks
ctx.is_admin (defense in depth — matters because render.py's Pass 2 re-runs
this resolver as the dashboard OWNER's identity, and a non-admin owner must
never get it to render just because an admin edit-shared it onto their
dashboard)."""

from services import ai_usage_service
from services.dashboard_blocks._tasks import _scoped_target
from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register
from services.file_service import read_json, user_path


def resolve_my_usage(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    usage = ai_usage_service.get_my_usage(target)
    return BlockRenderResult(ok=True, data={"usage": usage})


def resolve_usage_overview(ctx: BlockRenderCtx) -> BlockRenderResult:
    if not ctx.is_admin:
        return BlockRenderResult(ok=False, locked_reason="admin_only")
    overview = ai_usage_service.get_overview()
    rows = ai_usage_service.get_user_rows()
    return BlockRenderResult(ok=True, data={"overview": overview, "users": rows})


def resolve_recent_ai_actions(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    path = user_path(target) / "agent" / "runs.json"
    data = read_json(path, default={"runs": []})
    runs = data.get("runs", [])[-10:]
    runs.reverse()
    return BlockRenderResult(ok=True, data={"runs": runs})


register(
    BlockSpec(
        type="ai_usage_me",
        label="AI Usage — My Usage",
        category="live_aggregate",
        resolver=resolve_my_usage,
        scope_configurable=True,
    )
)
register(
    BlockSpec(
        type="ai_usage_overview",
        label="AI Usage — All Users Overview",
        category="live_aggregate",
        resolver=resolve_usage_overview,
        admin_only=True,
    )
)
register(
    BlockSpec(
        type="recent_ai_actions",
        label="Recent AI Actions",
        category="live_aggregate",
        resolver=resolve_recent_ai_actions,
        scope_configurable=True,
    )
)
