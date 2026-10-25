"""MCP server endpoint — POST /api/v1/mcp (Streamable HTTP transport, JSON
responses, stateless). Auth: `Authorization: Bearer lcos_…`, a personal API
key with the `mcp:read` or `mcp:write` scope. All protocol logic lives in
services/mcp_service.py; this file only does HTTP: origin/version checks,
body parsing, and turning the result into the right status code."""

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from routers.auth.deps import require_api_key
from services import mcp_service
from services.rate_limiter import rate_limit

router = APIRouter()

_mcp_ip_limit = rate_limit(120, 60)
_mcp_key = require_api_key(("mcp:read", "mcp:write"), max_calls=60, window_seconds=60)
_MAX_BODY = 1_000_000


def _check_transport_headers(request: Request, protocol_version: str) -> None:
    if not mcp_service.origin_allowed(request.headers.get("origin", "")):
        raise HTTPException(status_code=403, detail="Origin not allowed")
    if protocol_version and protocol_version not in mcp_service.SUPPORTED_PROTOCOL_VERSIONS:
        raise HTTPException(
            status_code=400, detail=f"Unsupported MCP-Protocol-Version: {protocol_version}"
        )


@router.post("")
async def mcp_post(
    request: Request,
    current_user: dict = Depends(_mcp_key),
    _rl: None = Depends(_mcp_ip_limit),
    mcp_protocol_version: str = Header(default=""),
):
    _check_transport_headers(request, mcp_protocol_version)
    raw = await request.body()
    if len(raw) > _MAX_BODY:
        raise HTTPException(status_code=413, detail="Request body too large")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(
            mcp_service._error(None, mcp_service.PARSE_ERROR, "Parse error"), status_code=400
        )

    # Tool execution does blocking Brain file I/O — keep it off the event loop.
    if isinstance(payload, list):  # 2025-03-26 batches
        if not payload:
            return JSONResponse(
                mcp_service._error(None, mcp_service.INVALID_REQUEST, "Empty batch"),
                status_code=400,
            )
        results = []
        for message in payload:
            out = await asyncio.to_thread(mcp_service.handle_message, message, current_user)
            if out is not None:
                results.append(out)
        return JSONResponse(results) if results else Response(status_code=202)

    out = await asyncio.to_thread(mcp_service.handle_message, payload, current_user)
    if out is None:
        return Response(status_code=202)
    return JSONResponse(out)


@router.get("")
@router.delete("")
def mcp_no_stream(_rl: None = Depends(_mcp_ip_limit)):
    """No server-initiated SSE stream and no sessions to end — the spec's
    answer for a server that offers neither is 405."""
    return Response(status_code=405, headers={"Allow": "POST"})
