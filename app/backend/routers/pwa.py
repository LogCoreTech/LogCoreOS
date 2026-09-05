"""Per-user accent-colored PWA manifest/icon. Item #31, 2026-09-04 UX Polish Batch.

`manifest.webmanifest` is authenticated (cookie, via get_current_user) so it
can read the caller's own accent_color and bake it into the icon URLs it
returns. The icon endpoint itself stays unauthenticated and takes the accent
as a query param instead — the manifest's own auth check is what ties an
accent value to a real user; the PNG bytes it points at are just a public
brand asset recolored by a plain hex string, nothing sensitive gated there.
Native <link>/<img> requests can't attach the app's Authorization header
anyway, only the httpOnly cookie — see get_background()'s identical pattern.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response

from routers.auth import _ACCENT_COLOR_RE, get_current_user
from services import icon_service

router = APIRouter()

_DEFAULT_ACCENT = "#f97316"
_ICON_FILES = {192: "icon-192.png", 512: "icon-512.png"}
_ICON_SOURCE_DIRS = [
    Path(__file__).parent.parent.parent / "frontend" / "dist",
    Path(__file__).parent.parent.parent / "frontend" / "public",
]


def _find_base_icon(filename: str) -> Path:
    for d in _ICON_SOURCE_DIRS:
        p = d / filename
        if p.is_file():
            return p
    raise HTTPException(status_code=404, detail=f"{filename} not found")


def _clean_accent(accent: str | None) -> str:
    return accent if accent and _ACCENT_COLOR_RE.match(accent) else _DEFAULT_ACCENT


@router.get("/icon-{size}.png")
def get_icon(size: int, accent: str | None = None):
    if size not in _ICON_FILES:
        raise HTTPException(status_code=404, detail="Unsupported icon size")
    clean_accent = _clean_accent(accent)
    base_path = _find_base_icon(_ICON_FILES[size])
    data = icon_service.recolor_icon(base_path, clean_accent)
    return Response(content=data, media_type="image/png")


@router.get("/manifest.webmanifest")
def get_manifest(current_user: dict = Depends(get_current_user)):
    accent = _clean_accent(current_user.get("accent_color"))
    accent_qs = quote(accent, safe="")
    manifest = {
        "name": "LogCore OS",
        "short_name": "LogCore",
        "description": "Your values-driven family life operating system",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#1a1a1a",
        "theme_color": accent,
        "orientation": "portrait-primary",
        "icons": [
            {
                "src": f"/api/v1/pwa/icon-192.png?accent={accent_qs}",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": f"/api/v1/pwa/icon-512.png?accent={accent_qs}",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }
    return Response(content=json.dumps(manifest), media_type="application/manifest+json")
