"""Collection block — the generic replacement for writing a new hand-coded
resolver every time a dashboard needs to show "many records of a kind."
Configured, not coded: pick a template, optionally a contact to link against,
which fields to show, and which select-type field (if any) is the status.

Deliberately Assets-only for v1 — Assets already have real per-template typed
fields (including `select`, which is what makes a status control possible at
all); Contacts have no per-instance template to pick display fields from.
"""

from services.assets_service import asset_links_contact, attach_templates, list_visible
from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register


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

    candidates = attach_templates(
        list_visible(ctx.viewer, ctx.workspace, is_admin=ctx.is_admin, viewer_role=ctx.viewer_role)
    )
    template = next((a.get("_template") for a in candidates if a.get("template_id") == template_id), None)
    assets = [
        a for a in candidates
        if a.get("template_id") == template_id and not a.get("archived")
    ]
    if link_contact_id:
        assets = [a for a in assets if asset_links_contact(a, a.get("_template"), link_contact_id)]

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
            "display_fields": [{"key": k, "label": _field_label(template, k)} for k in display_fields],
            "status_field": status_field,
            "status_options": status_options,
        },
    )


register(
    BlockSpec(
        type="collection",
        label="Collection (List/Board)",
        category="record_linked",
        resolver=resolve_collection,
        record_ref_fields={"link_contact_id": "contacts"},
    )
)
