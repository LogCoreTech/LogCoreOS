"""Action blocks — Navigate To… and Status/Archive Action.

Display-only on the backend: these resolvers exist purely to label a button
(a record's name, its current status) through the same read-through gate
every other record-linked block uses. The actual write — the part a click
performs — never runs through here at all. The frontend calls each target
module's own existing endpoint directly (PATCH /tasks/{id}, POST
/contacts/{id}/archive, PATCH /assets/{id}, etc.), so the click is gated by
that module's own real, already-correct rules under the clicking viewer's
own session — completely independent of the dashboard's own access or its
share_underlying_data toggle, with nothing new to keep in sync. See the
'Dashboard: Action Buttons + Full Mobile Editing' plan for the full reasoning
against a unified write endpoint.
"""

from services import assets_service, contacts_service, dashboards_service, events_service, finance_service
from services import n8n_service, notes_service, task_service
from services.dashboard_blocks._tasks import _scoped_target
from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register


def _resolve_record_title(ctx: BlockRenderCtx, module: str, record_id: str) -> str | None:
    """Best-effort display title for a nav_button's target, gated the same
    read-through way as every other record-linked block. Navigation itself
    never depends on this succeeding — a lookup failure just means a generic
    label is shown, it never blocks the button from rendering or working."""
    try:
        if module == "tasks":
            target = _scoped_target(ctx)
            task = task_service.get_task(target, record_id, ctx.workspace) if target else None
            return task.get("title") if task else None
        if module == "contacts":
            found = contacts_service.find_contact(
                ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, record_id
            )
            return found[1].get("name") if found else None
        if module == "assets":
            found = assets_service.find_asset(
                ctx.viewer, ctx.workspace, record_id, ctx.is_admin, viewer_role=ctx.viewer_role
            )
            return found["asset"].get("name") if found else None
        if module == "calendar":
            target = _scoped_target(ctx)
            event = events_service.get_event(target, record_id, ctx.workspace) if target else None
            return event.get("title") if event else None
        if module == "notes":
            found = notes_service.find_note_store(
                ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, record_id
            )
            return record_id.rsplit("/", 1)[-1] if found else None
        if module == "finance":
            found = finance_service.find_book(ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, record_id)
            return found[1].get("name") if found else None
        if module == "automations":
            target = _scoped_target(ctx)
            wf = n8n_service.find_workflow(record_id, target) if target else None
            return wf.get("name") if wf else None
        if module == "dashboard":
            found = dashboards_service.find_dashboard(
                ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, record_id
            )
            return found["dashboard"].get("name") if found else None
    except Exception:
        return None
    return None


def resolve_nav_button(ctx: BlockRenderCtx) -> BlockRenderResult:
    module = ctx.config.get("module")
    record_id = ctx.config.get("record_id")
    if not module:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    title = _resolve_record_title(ctx, module, record_id) if record_id else None
    return BlockRenderResult(
        ok=True,
        data={
            "module": module,
            "record_id": record_id,
            "section": ctx.config.get("section"),
            "title": title,
            "label": ctx.config.get("label"),
        },
    )


def resolve_status_button(ctx: BlockRenderCtx) -> BlockRenderResult:
    record_type = ctx.config.get("record_type")

    if record_type == "task":
        task_id = ctx.config.get("task_id")
        target = _scoped_target(ctx)
        if not task_id or target is None:
            return BlockRenderResult(ok=False, locked_reason="not_found")
        task = task_service.get_task(target, task_id, ctx.workspace)
        if task is None:
            return BlockRenderResult(ok=False, locked_reason="not_found")
        return BlockRenderResult(
            ok=True,
            data={
                "record_type": "task",
                "record_id": task_id,
                "title": task.get("title"),
                "current_status": task.get("status"),
                "target_status": ctx.config.get("new_status"),
                "label": ctx.config.get("label"),
            },
        )

    if record_type == "contact":
        contact_id = ctx.config.get("contact_id")
        if not contact_id:
            return BlockRenderResult(ok=False, locked_reason="not_found")
        found = contacts_service.find_contact(ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, contact_id)
        if found is None:
            return BlockRenderResult(ok=False, locked_reason="no_access")
        _store_user, contact, _access = found
        # Contacts have no admin-configurable per-field option system the way
        # Asset templates do, so the pickable field set is this small, fixed
        # list of genuinely enumerable Contact fields (never free text) — see
        # docs/MEMORY.md for why status/archive aren't offered here: contact
        # `status` is freeform text with no enum, and the owner explicitly
        # asked for real data updates over archiving. The actual PATCH is a
        # direct contactsApi.update() call on click, gated by that endpoint's
        # own real edit-access requirement — this resolver only labels it.
        contact_field = ctx.config.get("contact_field") or {}
        return BlockRenderResult(
            ok=True,
            data={
                "record_type": "contact",
                "record_id": contact_id,
                "title": contact.get("name"),
                "field_key": contact_field.get("field_key"),
                "field_value": contact_field.get("value"),
                "label": ctx.config.get("label"),
            },
        )

    if record_type == "asset":
        asset_id = ctx.config.get("asset_id")
        if not asset_id:
            return BlockRenderResult(ok=False, locked_reason="not_found")
        found = assets_service.find_asset(
            ctx.viewer, ctx.workspace, asset_id, ctx.is_admin, viewer_role=ctx.viewer_role
        )
        if found is None:
            return BlockRenderResult(ok=False, locked_reason="no_access")
        asset = found["asset"]
        select_field = ctx.config.get("select_field") or {}
        return BlockRenderResult(
            ok=True,
            data={
                "record_type": "asset",
                "record_id": asset_id,
                "title": asset.get("name"),
                "archived": bool(asset.get("archived")),
                "action": ctx.config.get("asset_action"),
                "field_key": select_field.get("field_key"),
                "field_value": select_field.get("value"),
                "label": ctx.config.get("label"),
            },
        )

    return BlockRenderResult(ok=False, locked_reason="not_found")


register(
    BlockSpec(
        type="nav_button",
        label="Navigate To…",
        category="action",
        resolver=resolve_nav_button,
        record_ref_fields={"record_id": "$module"},
    )
)
register(
    BlockSpec(
        type="status_button",
        label="Status/Archive Action",
        category="action",
        resolver=resolve_status_button,
        record_ref_fields={"task_id": "tasks", "contact_id": "contacts", "asset_id": "assets"},
    )
)
