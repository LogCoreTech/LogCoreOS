"""Asset blocks — Documents/Attachments, Linked Tasks, Linked Contact
(cross-pointer), My Assets Summary (live-aggregate counts by template), and
Collection (the generic "many records of a kind" block, folded in from the
old dashboard_blocks/_collections.py when assets/ converted 2026-08-27 —
deliberately Assets-only today per its own resolve_collection() docstring,
which anticipates future generalization to other record types; kept as one
real, currently-Assets-exclusive block rather than left ungated in core on
the strength of a hypothetical future need that hasn't materialized)."""

from services import assets_service, task_service
from services.dashboard_blocks.registry import (
    BlockRenderCtx,
    BlockRenderResult,
    BlockSpec,
    register,
    scoped_target,
)


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
    contact_keys = [
        f["key"] for f in (template or {}).get("fields", []) if f.get("type") == "contact"
    ]
    contact_ids = [asset["fields"][k] for k in contact_keys if asset.get("fields", {}).get(k)]
    return BlockRenderResult(ok=True, data={"contact_ids": contact_ids})


def resolve_my_assets_summary(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    items = assets_service.list_assets(target, ctx.workspace)
    counts: dict[str, int] = {}
    for a in items:
        if not a.get("archived"):
            counts[a.get("template", "")] = counts.get(a.get("template", ""), 0) + 1
    return BlockRenderResult(ok=True, data={"counts": counts})


def _field_label(template: dict | None, key: str) -> str:
    for f in (template or {}).get("fields", []):
        if f.get("key") == key:
            return f.get("label") or key
    return key


def _row(asset: dict, display_fields: list[str], status_field: str | None) -> dict:
    fields = asset.get("fields") or {}
    row = {"id": asset["id"], "name": asset.get("name", "")}
    row["fields"] = {k: fields.get(k) for k in display_fields}
    if status_field:
        row["status_value"] = fields.get(status_field)
    return row


def resolve_collection(ctx: BlockRenderCtx) -> BlockRenderResult:
    template_id = ctx.config.get("template_id")
    if not template_id:
        return BlockRenderResult(ok=False, locked_reason="not_found")

    link_contact_id = ctx.config.get("link_contact_id")  # a real id here — "$subject" is already
    # resolved to the dashboard's own subject_id before this resolver ever runs (render.py).

    candidates = assets_service.attach_templates(
        assets_service.list_visible(
            ctx.viewer, ctx.workspace, is_admin=ctx.is_admin, viewer_role=ctx.viewer_role
        )
    )
    template = next(
        (a.get("_template") for a in candidates if a.get("template_id") == template_id), None
    )
    assets = [
        a for a in candidates if a.get("template_id") == template_id and not a.get("archived")
    ]
    if link_contact_id:
        assets = [
            a
            for a in assets
            if assets_service.asset_links_contact(a, a.get("_template"), link_contact_id)
        ]

    display_fields = ctx.config.get("display_fields") or []
    status_field = ctx.config.get("status_field")
    rows = [_row(a, display_fields, status_field) for a in assets]

    status_options = None
    if status_field and template:
        fdef = next((f for f in template.get("fields", []) if f.get("key") == status_field), None)
        status_options = fdef.get("options") if fdef else None

    return BlockRenderResult(
        ok=True,
        data={
            "rows": rows,
            "count": len(rows),
            "view": ctx.config.get("view", "list"),
            "template_label": (template or {}).get("label"),
            "display_fields": [
                {"key": k, "label": _field_label(template, k)} for k in display_fields
            ],
            "status_field": status_field,
            "status_options": status_options,
        },
    )


register(
    BlockSpec(
        type="documents",
        label="Documents/Attachments",
        category="record_linked",
        resolver=resolve_documents,
        record_ref_fields={"asset_id": "assets"},
        module="assets",
    )
)
register(
    BlockSpec(
        type="linked_tasks",
        label="Linked Tasks",
        category="record_linked",
        resolver=resolve_linked_tasks,
        record_ref_fields={"asset_id": "assets"},
        module="assets",
    )
)
register(
    BlockSpec(
        type="linked_contact",
        label="Linked Contact",
        category="record_linked",
        resolver=resolve_linked_contact,
        record_ref_fields={"asset_id": "assets"},
        module="assets",
    )
)
register(
    BlockSpec(
        type="my_assets_summary",
        label="My Assets Summary",
        category="live_aggregate",
        resolver=resolve_my_assets_summary,
        scope_configurable=True,
        module="assets",
    )
)
register(
    BlockSpec(
        type="collection",
        label="Collection (List/Board)",
        category="record_linked",
        resolver=resolve_collection,
        record_ref_fields={"link_contact_id": "contacts"},
        module="assets",
    )
)
