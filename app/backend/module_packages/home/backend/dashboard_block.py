"""Smart Home block — favourites, personal workspace only. Reuses ha_service
as-is; no new backend aggregation."""

from services import ha_service
from services.dashboard_blocks._tasks import _scoped_target
from services.dashboard_blocks.registry import (
    BlockRenderCtx,
    BlockRenderResult,
    BlockSpec,
    register,
)


def resolve_home_favourites(ctx: BlockRenderCtx) -> BlockRenderResult:
    if ctx.workspace != "personal":
        return BlockRenderResult(ok=False, locked_reason="not_found")
    target = _scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    if not ha_service.is_configured():
        return BlockRenderResult(ok=True, data={"entities": []})
    try:
        fav_ids = set(ha_service.get_favourites(target))
        if not fav_ids:
            return BlockRenderResult(ok=True, data={"entities": []})
        states = ha_service.get_states()
        entities = [s for s in states if s.get("entity_id") in fav_ids]
    except Exception:
        entities = []
    return BlockRenderResult(ok=True, data={"entities": entities})


register(
    BlockSpec(
        type="home_favourites",
        label="Smart Home Favourites",
        category="live_aggregate",
        resolver=resolve_home_favourites,
        workspace="personal",
        scope_configurable=True,
        module="home",
    )
)
