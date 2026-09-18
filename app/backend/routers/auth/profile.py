"""Self-service `/me` endpoints (profile get/update, background image
upload/download/delete, `/today`) — split out of the old routers/auth.py.
See routers/auth/__init__.py's docstring for the full rationale of this
package split."""

import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services import auth_service
from services.file_service import user_path
from services.rate_limiter import rate_limit

from .deps import _validate_timezone, get_current_user

router = APIRouter()

# Rate limits
_me_limit = rate_limit(10, 60)  # 10 profile updates per minute
_get_me_limit = rate_limit(30, 60)  # 30 GET /me or /today per minute (polled endpoints)

_ACCENT_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_VALID_DARK_MODES = frozenset({"system", "light", "dark"})
_VALID_GRADIENT_IDS = frozenset({"none", "midnight", "sunset", "forest", "ocean", "aurora", "dusk"})
_VALID_DENSITIES = frozenset({"comfortable", "compact"})
_VALID_CORNER_STYLES = frozenset({"rounded", "sharp"})
_ALLOWED_BG_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
}
_BG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def _validate_accent_color(color: str) -> str:
    if not _ACCENT_COLOR_RE.match(color):
        raise HTTPException(
            status_code=400, detail="accent_color must be a 6-digit hex color like #f97316"
        )
    return color


def _validate_dark_mode(mode: str) -> str:
    if mode not in _VALID_DARK_MODES:
        raise HTTPException(status_code=400, detail="dark_mode must be one of: system, light, dark")
    return mode


def _validate_density(val: str) -> str:
    if val not in _VALID_DENSITIES:
        raise HTTPException(status_code=400, detail="density must be 'comfortable' or 'compact'")
    return val


def _validate_corner_style(val: str) -> str:
    if val not in _VALID_CORNER_STYLES:
        raise HTTPException(status_code=400, detail="corner_style must be 'rounded' or 'sharp'")
    return val


_VALID_TASKS_FILTERS = frozenset({"all", "pending", "done", "overdue"})
_VALID_TASKS_SORT_MODES = frozenset({"priority", "date", "alpha"})


def _validate_tasks_filter(val: str) -> str:
    if val not in _VALID_TASKS_FILTERS:
        raise HTTPException(
            status_code=400, detail="tasks_filter must be one of: all, pending, done, overdue"
        )
    return val


def _validate_tasks_sort_mode(val: str) -> str:
    if val not in _VALID_TASKS_SORT_MODES:
        raise HTTPException(
            status_code=400, detail="tasks_sort_mode must be one of: priority, date, alpha"
        )
    return val


def _validate_background(val: str) -> str:
    if val in ("none", "uploaded"):
        return val
    if val.startswith("gradient:") and val[len("gradient:") :] in _VALID_GRADIENT_IDS:
        return val
    raise HTTPException(
        status_code=400, detail="background must be 'none', 'uploaded', or 'gradient:<preset>'"
    )


def _find_user_background(user_name: str):
    user_dir = user_path(user_name)
    for ext in _ALLOWED_BG_TYPES.values():
        p = user_dir / f"background.{ext}"
        if p.exists():
            return p
    return None


_VALID_SHORTCUT_WORKSPACES = frozenset({"personal", "business"})


class MeUpdateRequest(BaseModel):
    timezone: str | None = Field(None, max_length=50)
    accent_color: str | None = Field(None, max_length=7)
    dark_mode: str | None = Field(None, max_length=10)
    background: str | None = Field(None, max_length=30)
    density: str | None = Field(None, max_length=15)
    corner_style: str | None = Field(None, max_length=10)
    shortcuts: dict | None = None  # {"personal": [...], "business": [...]}
    default_dashboard_id: dict | None = None  # {"personal": id|None, "business": id|None}
    # 2026-09-04 UX Polish Batch settings (items #3, #25 — #6 lives in the
    # existing suggestions_service.py config instead, not here, see that
    # service's own this_week_digest entry):
    command_palette_enabled: bool | None = None
    command_palette_actions: list[str] | None = None  # module ids to offer as quick-actions
    welcome_back_ai_summary_enabled: bool | None = None
    welcome_back_threshold_days: int | None = Field(None, ge=1, le=90)
    # Item #22 — the one concrete "resets on every navigation" case actually
    # found in the app (Tasks' own filter/sort, previously localStorage-only,
    # now server-side/per-account so it syncs across devices).
    tasks_filter: str | None = Field(None, max_length=15)
    tasks_sort_mode: str | None = Field(None, max_length=15)


@router.patch("/me")
def update_me(
    req: MeUpdateRequest,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_me_limit),
):
    """Update the current user's own profile fields."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "timezone" in updates:
        _validate_timezone(updates["timezone"])
    if "accent_color" in updates:
        _validate_accent_color(updates["accent_color"])
    if "dark_mode" in updates:
        _validate_dark_mode(updates["dark_mode"])
    if "background" in updates:
        _validate_background(updates["background"])
    if "density" in updates:
        _validate_density(updates["density"])
    if "corner_style" in updates:
        _validate_corner_style(updates["corner_style"])
    if "tasks_filter" in updates:
        _validate_tasks_filter(updates["tasks_filter"])
    if "tasks_sort_mode" in updates:
        _validate_tasks_sort_mode(updates["tasks_sort_mode"])
    if "shortcuts" in updates:
        sc = updates["shortcuts"]
        if not isinstance(sc, dict):
            raise HTTPException(status_code=400, detail="shortcuts must be an object")
        for ws_key, ids in sc.items():
            if ws_key not in _VALID_SHORTCUT_WORKSPACES:
                raise HTTPException(
                    status_code=400, detail=f"Invalid workspace key in shortcuts: {ws_key!r}"
                )
            if not isinstance(ids, list) or len(ids) > 4:
                raise HTTPException(
                    status_code=400,
                    detail="shortcuts per workspace must be a list of up to 4 module IDs",
                )
    if "default_dashboard_id" in updates:
        dd = updates["default_dashboard_id"]
        if not isinstance(dd, dict):
            raise HTTPException(status_code=400, detail="default_dashboard_id must be an object")
        for ws_key in dd:
            if ws_key not in _VALID_SHORTCUT_WORKSPACES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid workspace key in default_dashboard_id: {ws_key!r}",
                )
    if not updates:
        return {"ok": True}
    auth_service.update_user(current_user["id"], updates)
    return {"ok": True, **updates}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user), _rl: None = Depends(_get_me_limit)):
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "role": current_user["role"],
        "timezone": current_user.get("timezone", "UTC"),
        "feature_role": current_user.get("feature_role", "member"),
        "disabled_modules": current_user.get("disabled_modules", []),
        "pool_edit": current_user.get("pool_edit", []),
        "workspaces": current_user.get("workspaces", ["personal"]),
        "accent_color": current_user.get("accent_color"),
        "dark_mode": current_user.get("dark_mode", "system"),
        "background": current_user.get("background"),
        "density": current_user.get("density", "comfortable"),
        "corner_style": current_user.get("corner_style", "rounded"),
        "shortcuts": current_user.get("shortcuts", {}),
        "default_dashboard_id": current_user.get("default_dashboard_id", {}),
        "command_palette_enabled": current_user.get("command_palette_enabled", True),
        "command_palette_actions": current_user.get("command_palette_actions", []),
        "welcome_back_ai_summary_enabled": current_user.get(
            "welcome_back_ai_summary_enabled", False
        ),
        "welcome_back_threshold_days": current_user.get("welcome_back_threshold_days", 7),
        "tasks_filter": current_user.get("tasks_filter", "pending"),
        "tasks_sort_mode": current_user.get("tasks_sort_mode", "priority"),
    }


@router.post("/me/background")
async def upload_background(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_me_limit),
):
    ext = _ALLOWED_BG_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(
            status_code=400, detail="Only JPEG, PNG, WebP, or AVIF images are allowed"
        )
    data = await file.read()
    if len(data) > _BG_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 5 MB")
    user_dir = user_path(current_user["name"])
    for old_ext in _ALLOWED_BG_TYPES.values():
        (user_dir / f"background.{old_ext}").unlink(missing_ok=True)
    (user_dir / f"background.{ext}").write_bytes(data)
    auth_service.update_user(current_user["id"], {"background": "uploaded"})
    return {"ok": True}


@router.get("/me/background")
def get_background(current_user: dict = Depends(get_current_user)):
    bg = _find_user_background(current_user["name"])
    if not bg:
        raise HTTPException(status_code=404, detail="No background image uploaded")
    _ext_to_mime = {v: k for k, v in _ALLOWED_BG_TYPES.items()}
    mime = _ext_to_mime.get(bg.suffix.lstrip("."), "application/octet-stream")
    return FileResponse(str(bg), media_type=mime)


@router.delete("/me/background", status_code=204)
def delete_background(
    current_user: dict = Depends(get_current_user), _rl: None = Depends(_me_limit)
):
    user_dir = user_path(current_user["name"])
    for old_ext in _ALLOWED_BG_TYPES.values():
        (user_dir / f"background.{old_ext}").unlink(missing_ok=True)
    auth_service.update_user(current_user["id"], {"background": None})


@router.get("/today")
def get_today(current_user: dict = Depends(get_current_user), _rl: None = Depends(_get_me_limit)):
    """Return today's date in the user's local timezone (YYYY-MM-DD)."""
    return {"today": auth_service.today_for_user(current_user["name"]).isoformat()}
