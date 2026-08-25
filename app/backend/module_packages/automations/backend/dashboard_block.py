"""Automations blocks — Workflow Status (single workflow by id, reuses
n8n_service.find_workflow) and Inbox Summary (in-process count over
automation_inbox_service.load_store — not a new aggregation subsystem)."""

from module_packages.automations.backend import inbox_service as automation_inbox_service
from services import n8n_service
from services.dashboard_blocks.registry import (
    BlockRenderCtx,
    BlockRenderResult,
    BlockSpec,
    register,
    scoped_target,
)


def resolve_workflow_status(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = scoped_target(ctx)
    record_id = ctx.config.get("workflow_id")
    if target is None or not record_id:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    wf = n8n_service.find_workflow(record_id, target)
    if wf is None:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    return BlockRenderResult(ok=True, data={"workflow": wf})


def resolve_inbox_summary(ctx: BlockRenderCtx) -> BlockRenderResult:
    target = scoped_target(ctx)
    if target is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    # Personal scope -> the viewer's own inbox store; business scope -> the
    # _team pool store, same routing automations.py itself uses.
    store_user = "_team" if ctx.workspace == "business" else target
    try:
        store = automation_inbox_service.load_store(store_user)
    except Exception:
        return BlockRenderResult(ok=True, data={"new_count": 0, "total": 0})
    items = store.get("items", [])
    new_count = sum(1 for i in items if i.get("status") == "new")
    return BlockRenderResult(ok=True, data={"new_count": new_count, "total": len(items)})


register(
    BlockSpec(
        type="workflow_status",
        label="Automation Workflow Status",
        category="record_linked",
        resolver=resolve_workflow_status,
        scope_configurable=True,
        record_ref_fields={"workflow_id": "automations"},
        module="automations",
    )
)
register(
    BlockSpec(
        type="inbox_summary",
        label="Automation Inbox Summary",
        category="live_aggregate",
        resolver=resolve_inbox_summary,
        scope_configurable=True,
        module="automations",
    )
)
