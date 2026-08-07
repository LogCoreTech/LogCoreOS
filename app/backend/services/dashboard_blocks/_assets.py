"""Asset blocks — Documents/Attachments, Linked Tasks, Linked Contact
(cross-pointer), and My Assets Summary (live-aggregate counts by template)."""

from services import assets_service, task_service
from services.dashboard_blocks._tasks import _scoped_target
from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register


def _find(ctx: BlockRenderCtx, asset_id: str):
    return assets_service.find_asset(
        ctx.viewer, ctx.workspace, asset_id, ctx.is_admin, viewer_role=ctx.viewer_role
    )


def resolve_documents(ctx: BlockRenderCtx) -> BlockRenderResult:
    asset_id = ctx.config.get("asset_id")
    if not asset_id:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    found = _find(ctx, asset_id)
    if found is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    return BlockRenderResult(
        ok=True,
        data={"asset_id": asset_id, "attachments": found["asset"].get("attachments", [])},
    )


def resolve_linked_tasks(ctx: BlockRenderCtx) -> BlockRenderResult:
    asset_id = ctx.config.get("asset_id")
    if not asset_id:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    found = _find(ctx, asset_id)
    if found is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    all_tasks = task_service.list_tasks(found["store"], found["store_workspace"])
    linked = [t for t in all_tasks if t.get("asset_id") == asset_id]
    return BlockRenderResult(ok=True, data={"tasks": linked})


def resolve_linked_contact(ctx: BlockRenderCtx) -> BlockRenderResult:
    """Asset -> its own `contact`-type template field."""
    asset_id = ctx.config.get("asset_id")
    if not asset_id:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    found = _find(ctx, asset_id)
    if found is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    asset = found["asset"]
    template = assets_service.resolve_template(asset)
    contact_keys = [f["key"] for f in (template or {}).get("fields", []) if f.get("type") == "contact"]
    contact_ids = [asset["fields"][k] for k in contact_keys if asset.get("fields", {}).get(k)]
    return BlockRenderResult(ok=True, data={"contact_ids": contact_ids})


def resolve_my_assets_summary(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = _scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    items = assets_service.list_assets(target, ctx.workspace)
    counts: dict[str, int] = {}
    for a in items:
        if not a.get("archived"):
            counts[a.get("template", "")] = counts.get(a.get("template", ""), 0) + 1
    return BlockRenderResult(ok=True, data={"counts": counts})


register(
    BlockSpec(
        type="documents",
        label="Documents/Attachments",
        category="record_linked",
        resolver=resolve_documents,
        record_ref_fields={"asset_id": "assets"},
    )
)
register(
    BlockSpec(
        type="linked_tasks",
        label="Linked Tasks",
        category="record_linked",
        resolver=resolve_linked_tasks,
        record_ref_fields={"asset_id": "assets"},
    )
)
register(
    BlockSpec(
        type="linked_contact",
        label="Linked Contact",
        category="record_linked",
        resolver=resolve_linked_contact,
        record_ref_fields={"asset_id": "assets"},
    )
)
register(
    BlockSpec(
        type="my_assets_summary",
        label="My Assets Summary",
        category="live_aggregate",
        resolver=resolve_my_assets_summary,
        scope_configurable=True,
    )
)
