"""Tests for routers/pwa.py — item #31, 2026-09-04 UX Polish Batch."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from routers.pwa import get_icon, get_manifest


@pytest.fixture()
def alice(brain):
    from services import auth_service

    user = auth_service.create_user("alice@example.com", "password123", "Alice")
    yield user
    auth_service._revoked_jtis.clear()


def test_get_icon_returns_png_for_valid_size():
    resp = get_icon(192, accent="#3b82f6")
    assert resp.media_type == "image/png"
    assert resp.body[:8] == b"\x89PNG\r\n\x1a\n"


def test_get_icon_rejects_unsupported_size():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        get_icon(64, accent="#3b82f6")
    assert exc.value.status_code == 404


def test_get_icon_falls_back_to_default_accent_on_bad_input():
    # Malformed hex must not raise — it should silently fall back rather than
    # ever reach int(..., 16) with attacker-controlled input.
    resp = get_icon(192, accent="javascript:alert(1)")
    assert resp.media_type == "image/png"
    assert resp.body[:8] == b"\x89PNG\r\n\x1a\n"


def test_get_icon_with_no_accent_uses_default():
    resp = get_icon(192, accent=None)
    assert resp.body[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_get_manifest_bakes_user_accent_into_icon_urls(alice):
    from services import auth_service

    auth_service.update_user(alice["id"], {"accent_color": "#22c55e"})
    alice["accent_color"] = "#22c55e"

    resp = get_manifest(alice)
    assert resp.media_type == "application/manifest+json"
    manifest = json.loads(resp.body)
    assert manifest["theme_color"] == "#22c55e"
    for icon in manifest["icons"]:
        # The '#' must be percent-encoded (%23) — a raw '#' in a URL starts a
        # fragment, so the accent value would never actually reach the server.
        assert "accent=%2322c55e" in icon["src"]
        assert "#22c55e" not in icon["src"].split("?", 1)[1]


@pytest.mark.asyncio
async def test_get_manifest_falls_back_to_brand_default_with_no_accent(alice):
    resp = get_manifest(alice)
    manifest = json.loads(resp.body)
    assert manifest["theme_color"] == "#f97316"
