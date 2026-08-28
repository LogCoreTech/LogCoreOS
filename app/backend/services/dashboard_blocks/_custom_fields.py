"""Custom Fields block — genuinely reads from EITHER contacts_service OR
assets_service depending on which config field is set (record_ref_fields
declares both contact_id and asset_id). Split out of the old _contacts.py
when Contacts converted into module_packages/contacts/ (2026-08-28) — the
other three blocks that file registered (linked_deals, contacts_list,
linked_assets) are exclusively Contacts' own and moved into that package,
but this one spans two modules and belongs to neither, the same
"owned by none" shape as _actions.py's nav_button/status_button. Left
ungated by module= for the same reason those are: gating it to either
module alone would incorrectly hide it when the OTHER module is the one
actually disabled."""

from services import assets_service, contacts_service
from services.dashboard_blocks.registry import (
    BlockRenderCtx,
    BlockRenderResult,
    BlockSpec,
    register,
)


def resolve_custom_fields(ctx: BlockRenderCtx) -> BlockRenderResult:
    contact_id = ctx.config.get("contact_id")
    asset_id = ctx.config.get("asset_id")
    if contact_id:
        found = contacts_service.find_contact(
            ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, contact_id
        )
        if found is None:
            return BlockRenderResult(ok=False, locked_reason="no_access")
        _store_user, contact, _access = found
        return BlockRenderResult(
            ok=True, data={"fields": contact.get("custom", {}), "name": contact.get("name")}
        )
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
            data={
                "fields": asset.get("fields", {}),
                "template": template,
                "name": asset.get("name"),
            },
        )
    return BlockRenderResult(ok=False, locked_reason="not_found")


register(
    BlockSpec(
        type="custom_fields",
        label="Custom Fields",
        category="record_linked",
        resolver=resolve_custom_fields,
        record_ref_fields={"contact_id": "contacts", "asset_id": "assets"},
    )
)
