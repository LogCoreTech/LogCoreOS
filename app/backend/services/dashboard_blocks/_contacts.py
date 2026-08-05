"""Contact blocks — Linked Deals, Custom Fields, Linked Assets (cross-pointer).
Reuses contacts_service.find_contact — the SAME gate the Contacts router uses."""

from services import assets_service, contacts_service
from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register


def resolve_linked_deals(ctx: BlockRenderCtx) -> BlockRenderResult:
    contact_id = ctx.config.get("contact_id")
    if not contact_id:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    found = contacts_service.find_contact(ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, contact_id)
    if found is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    store_user, contact, _access = found
    deals = contacts_service.list_deals(store_user, ctx.workspace, contact_id)
    return BlockRenderResult(ok=True, data={"deals": deals, "contact_name": contact.get("name")})


def resolve_custom_fields(ctx: BlockRenderCtx) -> BlockRenderResult:
    contact_id = ctx.config.get("contact_id")
    asset_id = ctx.config.get("asset_id")
    if contact_id:
        found = contacts_service.find_contact(ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, contact_id)
        if found is None:
            return BlockRenderResult(ok=False, locked_reason="no_access")
        _store_user, contact, _access = found
        return BlockRenderResult(ok=True, data={"fields": contact.get("custom", {}), "name": contact.get("name")})
    if asset_id:
        found = assets_service.find_asset(
            ctx.viewer, ctx.workspace, asset_id, ctx.is_admin, viewer_role=ctx.viewer_role
        )
        if found is None:
            return BlockRenderResult(ok=False, locked_reason="no_access")
        asset = found["asset"]
        template = assets_service.resolve_template(asset)
        return BlockRenderResult(
            ok=True,
            data={"fields": asset.get("fields", {}), "template": template, "name": asset.get("name")},
        )
    return BlockRenderResult(ok=False, locked_reason="not_found")


def resolve_linked_assets(ctx: BlockRenderCtx) -> BlockRenderResult:
    """Contact -> reverse lookup of Assets referencing it via a `contact` field."""
    contact_id = ctx.config.get("contact_id")
    if not contact_id:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    found = contacts_service.find_contact(ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, contact_id)
    if found is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    assets = assets_service.list_assets_for_contact(
        ctx.viewer, ctx.workspace, contact_id, ctx.is_admin, viewer_role=ctx.viewer_role
    )
    return BlockRenderResult(ok=True, data={"assets": assets})


register(
    BlockSpec(
        type="linked_deals",
        label="Linked Deals",
        category="record_linked",
        resolver=resolve_linked_deals,
        record_ref_fields={"contact_id": "contacts"},
    )
)
register(
    BlockSpec(
        type="custom_fields",
        label="Custom Fields",
        category="record_linked",
        resolver=resolve_custom_fields,
        record_ref_fields={"contact_id": "contacts", "asset_id": "assets"},
    )
)
register(
    BlockSpec(
        type="linked_assets",
        label="Linked Assets",
        category="record_linked",
        resolver=resolve_linked_assets,
        record_ref_fields={"contact_id": "contacts"},
    )
)
