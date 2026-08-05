"""Freeform blocks — Text, Custom Link/Button, Heading/Divider. No external
data, so no access gate needed; config is stored inline on the dashboard
itself, which is already access-controlled at the dashboard level."""

import re

from services.dashboard_blocks.registry import BlockRenderCtx, BlockRenderResult, BlockSpec, register

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def resolve_text_block(ctx: BlockRenderCtx) -> BlockRenderResult:
    text = str(ctx.config.get("text") or "")[:5000]
    return BlockRenderResult(ok=True, data={"text": text})


def resolve_link_button(ctx: BlockRenderCtx) -> BlockRenderResult:
    url = str(ctx.config.get("url") or "")
    label = str(ctx.config.get("label") or "Link")[:100]
    if url and not _URL_RE.match(url):
        # Scheme-invalid config — render nothing rather than a javascript:/data:
        # link (mirrors InboxItemIn's validator in routers/automations.py).
        return BlockRenderResult(ok=True, data={"url": "", "label": label})
    return BlockRenderResult(ok=True, data={"url": url, "label": label})


def resolve_heading_divider(ctx: BlockRenderCtx) -> BlockRenderResult:
    text = str(ctx.config.get("text") or "")[:200]
    style = ctx.config.get("style") if ctx.config.get("style") in ("heading", "divider") else "heading"
    return BlockRenderResult(ok=True, data={"text": text, "style": style})


register(BlockSpec(type="text_block", label="Text", category="freeform", resolver=resolve_text_block))
register(
    BlockSpec(type="link_button", label="Custom Link/Button", category="freeform", resolver=resolve_link_button)
)
register(
    BlockSpec(
        type="heading_divider", label="Heading/Divider", category="freeform", resolver=resolve_heading_divider
    )
)
