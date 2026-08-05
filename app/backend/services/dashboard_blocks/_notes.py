"""Note Embed block — reuses notes_service.find_note_store, the same gate the
Notes router uses."""

from services import notes_service
from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register


def resolve_note_embed(ctx: BlockRenderCtx) -> BlockRenderResult:
    path = ctx.config.get("path")
    if not path:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    found = notes_service.find_note_store(ctx.viewer, ctx.viewer_role, ctx.is_admin, ctx.workspace, path)
    if found is None:
        return BlockRenderResult(ok=False, locked_reason="no_access")
    store_user, _access = found
    note = notes_service.get_note(store_user, path, ctx.workspace)
    if note is None:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    content = note.get("content", "")
    return BlockRenderResult(ok=True, data={"path": path, "preview": content[:400]})


register(
    BlockSpec(
        type="note_embed",
        label="Note Embed",
        category="record_linked",
        resolver=resolve_note_embed,
        record_ref_fields={"path": "notes"},
    )
)
