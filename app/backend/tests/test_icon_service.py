"""Tests for services/icon_service.py — item #31, 2026-09-04 UX Polish Batch."""

import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.icon_service import recolor_icon

_ICON_PATH = Path(__file__).parent.parent.parent / "frontend" / "public" / "icon-192.png"


def _find_orange_pixel(im: Image.Image) -> tuple[int, int]:
    """Locate a pixel inside the shipped icon's orange 'C' glyph."""
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = im.getpixel((x, y))
            if a > 200 and r > 200 and g > 90 and g < 160 and b < 90:
                return x, y
    raise AssertionError("no orange pixel found in source icon — has it changed?")


def _hue_deg(rgb: tuple[int, int, int]) -> float:
    h = Image.new("RGB", (1, 1), rgb).convert("HSV").getpixel((0, 0))[0]
    return h / 255 * 360


def test_recolor_produces_valid_png_at_requested_size():
    data = recolor_icon(_ICON_PATH, "#3b82f6")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    out = Image.open(io.BytesIO(data))
    assert out.size == Image.open(_ICON_PATH).size


def test_recolor_shifts_the_orange_glyph_toward_the_target_hue():
    original = Image.open(_ICON_PATH).convert("RGBA")
    x, y = _find_orange_pixel(original)

    recolored = Image.open(io.BytesIO(recolor_icon(_ICON_PATH, "#3b82f6"))).convert("RGBA")
    orig_rgb = original.getpixel((x, y))[:3]
    new_rgb = recolored.getpixel((x, y))[:3]

    orig_hue = _hue_deg(orig_rgb)
    new_hue = _hue_deg(new_rgb)
    target_hue = _hue_deg((0x3B, 0x82, 0xF6))

    assert abs(new_hue - target_hue) < 5
    assert abs(new_hue - orig_hue) > 30


def test_recolor_leaves_background_and_white_glyph_untouched():
    original = Image.open(_ICON_PATH).convert("RGBA")
    recolored = Image.open(io.BytesIO(recolor_icon(_ICON_PATH, "#3b82f6"))).convert("RGBA")

    # Top-left corner is the dark badge background on both shipped icon sizes.
    assert original.getpixel((0, 0)) == recolored.getpixel((0, 0))

    # A near-white pixel (part of the "L") is hue-invariant regardless of any
    # rotation applied, since its saturation is ~0.
    for y in range(original.height):
        for x in range(original.width):
            r, g, b, a = original.getpixel((x, y))
            if a > 200 and r > 240 and g > 240 and b > 240:
                assert recolored.getpixel((x, y)) == (r, g, b, a)
                return
    raise AssertionError("no near-white pixel found in source icon — has it changed?")


def test_recolor_to_brand_default_is_near_identity():
    recolored = Image.open(io.BytesIO(recolor_icon(_ICON_PATH, "#f97316"))).convert("RGBA")
    original = Image.open(_ICON_PATH).convert("RGBA")
    x, y = _find_orange_pixel(original)
    orig_rgb = original.getpixel((x, y))[:3]
    new_rgb = recolored.getpixel((x, y))[:3]
    assert abs(_hue_deg(orig_rgb) - _hue_deg(new_rgb)) < 3
