"""Household/Team pool tasks block — reuses task_service.list_tasks against the
pool pseudo-user (same store shared.py/team.py already read from). Pool task
reads are open to any member with the module enabled — no per-viewer gate to
enforce here, unlike personal-scope blocks."""

from services import task_service
from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register

_POOL_USER = {"personal": "_household", "business": "_team"}


def resolve_pool_tasks(ctx: BlockRenderCtx) -> BlockRenderResult:
    pool_user = _POOL_USER.get(ctx.workspace)
    if pool_user is None:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    all_tasks = task_service.list_tasks(pool_user, "personal")
    pending = [t for t in all_tasks if t.get("status") == "pending"][:5]
    return BlockRenderResult(ok=True, data={"tasks": pending})


register(
    BlockSpec(
        type="pool_tasks",
        label="Household/Team Pool Tasks",
        category="live_aggregate",
        resolver=resolve_pool_tasks,
    )
)
