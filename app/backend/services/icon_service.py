"""Per-user accent-colored PWA icon generation.

Item #31, 2026-09-04 UX Polish Batch. `icon-192.png`/`icon-512.png` are a flat
orange "C" (LogCore's brand accent, `#f97316`, hue ~24 deg) on a dark badge
with a white "L". Rather than re-drawing the glyph, this rotates only the
pixels near that source hue to the target accent's hue and leaves saturation
and value untouched, so the glyph's existing shading/anti-aliasing survives.
The dark badge (hue ~213 deg) and white "L" (near-zero saturation, hue-
invariant in appearance) fall outside the hue window and are never touched.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

_SOURCE_HUE_DEG = 24  # sampled from the shipped icon's orange (~rgb 234,126,54)
_HUE_WINDOW_DEG = 45  # wide enough to catch anti-aliased edge pixels


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def recolor_icon(base_path: Path, accent_hex: str) -> bytes:
    base = Image.open(base_path).convert("RGBA")
    r, g, b, a = base.split()
    h_ch, s_ch, v_ch = Image.merge("RGB", (r, g, b)).convert("HSV").split()

    target_rgb = _hex_to_rgb(accent_hex)
    target_hue = Image.new("RGB", (1, 1), target_rgb).convert("HSV").getpixel((0, 0))[0]

    source_hue = round(_SOURCE_HUE_DEG / 360 * 255)
    window = round(_HUE_WINDOW_DEG / 360 * 255)
    shift = (target_hue - source_hue) % 256

    def remap(h_val: int) -> int:
        dist = min((h_val - source_hue) % 256, (source_hue - h_val) % 256)
        return (h_val + shift) % 256 if dist <= window else h_val

    new_h = h_ch.point(remap)
    new_rgb = Image.merge("HSV", (new_h, s_ch, v_ch)).convert("RGB")
    out = Image.merge("RGBA", (*new_rgb.split(), a))

    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
