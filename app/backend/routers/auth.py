import re
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import settings
from services import auth_service
from services.file_service import brain_path, read_json, user_path, write_json
from services.rate_limiter import rate_limit

router = APIRouter()
bearer_optional = HTTPBearer(auto_error=False)

_COOKIE = "lc_token"

# Rate limits
_login_limit    = rate_limit(5, 300)    # 5 login attempts per 5 min
_register_limit = rate_limit(3, 3600)   # 3 registrations per hour
_me_limit       = rate_limit(10, 60)    # 10 profile updates per minute
_get_me_limit   = rate_limit(30, 60)    # 30 GET /me or /today per minute (polled endpoints)
_status_limit   = rate_limit(20, 60)    # 20 /status checks per minute (public)
_admin_limit    = rate_limit(20, 60)    # 20 admin ops per minute


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=1, max_length=60)
    session_minutes: int = Field(default=10080, ge=60, le=129600)  # 1h–90 days


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SessionRequest(BaseModel):
    session_minutes: int = Field(..., ge=60, le=129600)


def _set_auth_cookie(response: Response, token: str, session_minutes: int) -> None:
    response.set_cookie(
        key=_COOKIE,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=session_minutes * 60,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=_COOKIE, path="/", samesite="lax")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_optional),
) -> dict:
    # Accept httpOnly cookie first, then fall back to Authorization header
    token = request.cookies.get(_COOKIE)
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = auth_service.decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = auth_service.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    # Attach jti and exp so logout can revoke with persistence
    user["_jti"] = payload.get("jti")
    user["_exp"] = payload.get("exp")
    return user


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def require_module(module_id: str):
    """Dependency factory — blocks the endpoint if the module is disabled for this user."""
    def check(current_user: dict = Depends(get_current_user)) -> dict:
        if module_id in current_user.get("disabled_modules", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module_id}' has been disabled for your account.",
            )
        return current_user
    return check


@router.get("/status")
def registration_status(_rl: None = Depends(_status_limit)):
    """Public endpoint — lets the login page know if self-registration is available."""
    runtime = auth_service.get_system_settings()
    allow = runtime.get("allow_open_registration", settings.allow_open_registration)
    return {"registration_open": auth_service.user_count() == 0 or allow}


@router.post("/register")
def register(
    req: RegisterRequest,
    response: Response,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_optional),
    _rl: None = Depends(_register_limit),
):
    is_first_user = auth_service.user_count() == 0

    # Runtime setting (admin-toggleable via UI) takes precedence over the env var
    runtime = auth_service.get_system_settings()
    allow_open = runtime.get("allow_open_registration", settings.allow_open_registration)

    if not is_first_user and not allow_open:
        # Allow cookie-based admin auth as well
        admin_token = request.cookies.get(_COOKIE)
        if not admin_token and credentials:
            admin_token = credentials.credentials
        if not admin_token:
            raise HTTPException(status_code=403, detail="Registration is closed. An admin must add new users.")
        payload = auth_service.decode_token(admin_token)
        if not payload or payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins can register new users.")

    role = "admin" if is_first_user else "member"
    try:
        user = auth_service.create_user(
            req.email, req.password, req.name,
            role=role,
            session_minutes=req.session_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = auth_service.create_token(user)
    _set_auth_cookie(response, token, user.get("session_minutes", 10080))
    return {
        "id":               user["id"],
        "name":             user["name"],
        "role":             user["role"],
        "disabled_modules": user.get("disabled_modules", []),
        "timezone":         user.get("timezone", "UTC"),
        "accent_color":     user.get("accent_color"),
        "dark_mode":        user.get("dark_mode", "system"),
        "background":       user.get("background"),
        "density":          user.get("density", "comfortable"),
        "corner_style":     user.get("corner_style", "rounded"),
    }


@router.post("/login")
def login(req: LoginRequest, response: Response, _rl: None = Depends(_login_limit)):
    user = auth_service.authenticate(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth_service.create_token(user)
    _set_auth_cookie(response, token, user.get("session_minutes", 10080))
    return {
        "id":               user["id"],
        "name":             user["name"],
        "role":             user["role"],
        "disabled_modules": user.get("disabled_modules", []),
        "timezone":         user.get("timezone", "UTC"),
        "accent_color":     user.get("accent_color"),
        "dark_mode":        user.get("dark_mode", "system"),
        "background":       user.get("background"),
        "density":          user.get("density", "comfortable"),
        "corner_style":     user.get("corner_style", "rounded"),
    }


@router.post("/logout")
def logout(response: Response, current_user: dict = Depends(get_current_user)):
    jti = current_user.get("_jti")
    exp = current_user.get("_exp")
    if jti:
        auth_service.revoke_token(jti, exp)
    _clear_auth_cookie(response)
    return {"ok": True}


@router.post("/token")
def get_token(req: LoginRequest):
    """Return a plain Bearer token for CLI / programmatic clients.
    Browser sessions should use /login (sets HttpOnly cookie instead)."""
    user = auth_service.authenticate(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"token": auth_service.create_token(user)}


def _validate_timezone(tz: str) -> str:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, Exception):
        raise HTTPException(status_code=400, detail=f"Invalid timezone: '{tz}'. Use an IANA zone name like 'America/Chicago'.")
    return tz


_ACCENT_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
_VALID_DARK_MODES = frozenset({"system", "light", "dark"})
_VALID_GRADIENT_IDS = frozenset({"none", "midnight", "sunset", "forest", "ocean", "aurora", "dusk"})
_VALID_DENSITIES = frozenset({"comfortable", "compact"})
_VALID_CORNER_STYLES = frozenset({"rounded", "sharp"})
_ALLOWED_BG_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png":  "png",
    "image/webp": "webp",
    "image/avif": "avif",
}
_BG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def _validate_accent_color(color: str) -> str:
    if not _ACCENT_COLOR_RE.match(color):
        raise HTTPException(status_code=400, detail="accent_color must be a 6-digit hex color like #f97316")
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


def _validate_background(val: str) -> str:
    if val in ("none", "uploaded"):
        return val
    if val.startswith("gradient:") and val[len("gradient:"):] in _VALID_GRADIENT_IDS:
        return val
    raise HTTPException(status_code=400, detail="background must be 'none', 'uploaded', or 'gradient:<preset>'")


def _find_user_background(user_name: str):
    user_dir = user_path(user_name)
    for ext in _ALLOWED_BG_TYPES.values():
        p = user_dir / f"background.{ext}"
        if p.exists():
            return p
    return None


class MeUpdateRequest(BaseModel):
    timezone:     str | None = Field(None, max_length=50)
    accent_color: str | None = Field(None, max_length=7)
    dark_mode:    str | None = Field(None, max_length=10)
    background:   str | None = Field(None, max_length=30)
    density:      str | None = Field(None, max_length=15)
    corner_style: str | None = Field(None, max_length=10)


@router.patch("/me")
def update_me(req: MeUpdateRequest, current_user: dict = Depends(get_current_user), _rl: None = Depends(_me_limit)):
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
    if not updates:
        return {"ok": True}
    auth_service.update_user(current_user["id"], updates)
    return {"ok": True, **updates}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user), _rl: None = Depends(_get_me_limit)):
    return {
        "id":                   current_user["id"],
        "name":                 current_user["name"],
        "role":                 current_user["role"],
        "notification_channel": current_user.get("notification_channel", ""),
        "session_minutes":      current_user.get("session_minutes", 10080),
        "timezone":             current_user.get("timezone", "UTC"),
        "disabled_modules":     current_user.get("disabled_modules", []),
        "accent_color":         current_user.get("accent_color"),
        "dark_mode":            current_user.get("dark_mode", "system"),
        "background":           current_user.get("background"),
        "density":              current_user.get("density", "comfortable"),
        "corner_style":         current_user.get("corner_style", "rounded"),
    }


@router.post("/me/background")
async def upload_background(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_me_limit),
):
    ext = _ALLOWED_BG_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WebP, or AVIF images are allowed")
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
def delete_background(current_user: dict = Depends(get_current_user), _rl: None = Depends(_me_limit)):
    user_dir = user_path(current_user["name"])
    for old_ext in _ALLOWED_BG_TYPES.values():
        (user_dir / f"background.{old_ext}").unlink(missing_ok=True)
    auth_service.update_user(current_user["id"], {"background": None})


@router.get("/users")
def list_users_legacy(current_user: dict = Depends(require_admin)):
    """List all users without sensitive fields (admin only)."""
    data = auth_service._load_auth()
    safe_fields = {"id", "name", "email", "role", "timezone", "disabled_modules", "created_at"}
    return [
        {k: v for k, v in u.items() if k in safe_fields}
        for u in data["users"]
    ]


class RoleUpdateRequest(BaseModel):
    role: Literal["admin", "member"]


@router.patch("/users/{user_id}/role")
def update_user_role_legacy(
    user_id: str,
    req: RoleUpdateRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Promote or demote a user's role (admin only)."""
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    user = auth_service.update_user(user_id, {"role": req.role})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "role": req.role}


VALID_MODULE_IDS = {"dashboard", "tasks", "calendar", "goals", "household", "chat", "brain", "settings"}


class ModuleAccessRequest(BaseModel):
    disabled_modules: list[str]

    @field_validator("disabled_modules")
    @classmethod
    def validate_module_ids(cls, v: list[str]) -> list[str]:
        invalid = [m for m in v if m not in VALID_MODULE_IDS]
        if invalid:
            raise ValueError(f"Unknown module IDs: {invalid}")
        return v


@router.patch("/users/{user_id}/modules")
def update_user_modules(
    user_id: str,
    req: ModuleAccessRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Set which modules are disabled for a given user (admin only)."""
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Admins cannot restrict their own module access")
    user = auth_service.update_user(user_id, {"disabled_modules": req.disabled_modules})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "disabled_modules": req.disabled_modules}


class UserUpdateRequest(BaseModel):
    timezone: str | None = Field(None, max_length=50)


@router.patch("/users/{user_id}")
def update_user_by_admin(
    user_id: str,
    req: UserUpdateRequest,
    current_user: dict = Depends(require_admin),
):
    """Update user fields that admins control (timezone, etc.)."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "timezone" in updates:
        _validate_timezone(updates["timezone"])
    if not updates:
        return {"ok": True}
    user = auth_service.update_user(user_id, updates)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, **updates}


_session_limit = rate_limit(5, 3600)   # 5 session updates per hour


@router.patch("/session")
def update_session(
    req: SessionRequest,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_session_limit),
):
    """Update session length for the current user."""
    auth_service.update_user(current_user["id"], {"session_minutes": req.session_minutes})
    return {"ok": True, "session_minutes": req.session_minutes}


@router.get("/today")
def get_today(current_user: dict = Depends(get_current_user), _rl: None = Depends(_get_me_limit)):
    """Return today's date in the user's local timezone (YYYY-MM-DD)."""
    return {"today": auth_service.today_for_user(current_user["name"]).isoformat()}


# ---------------------------------------------------------------------------
# Admin — AI provider settings
# ---------------------------------------------------------------------------

_AI_SETTINGS_PATH = brain_path() / "ai_settings.json"


class AiSettingsRequest(BaseModel):
    ai_provider: Literal["anthropic", "openai"]
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = ""


@router.get("/admin/ai-settings")
def get_ai_settings(current_user: dict = Depends(require_admin)):
    stored = read_json(_AI_SETTINGS_PATH, default={})
    provider = stored.get("ai_provider", settings.ai_provider)
    model = stored.get("ai_model", settings.ai_model)
    base_url = stored.get("ai_base_url", "")
    # Key is "set" if present in file or in env (for Anthropic)
    key_set = bool(
        stored.get("ai_api_key")
        or (provider == "anthropic" and settings.anthropic_api_key)
    )
    return {
        "ai_provider": provider,
        "ai_model": model,
        "ai_api_key_set": key_set,
        "ai_base_url": base_url,
    }


@router.patch("/admin/ai-settings")
def update_ai_settings(
    req: AiSettingsRequest,
    current_user: dict = Depends(require_admin),
):
    stored = read_json(_AI_SETTINGS_PATH, default={})
    stored["ai_provider"] = req.ai_provider
    stored["ai_base_url"] = req.ai_base_url
    if req.ai_model:
        stored["ai_model"] = req.ai_model
    if req.ai_api_key:
        stored["ai_api_key"] = req.ai_api_key
    write_json(_AI_SETTINGS_PATH, stored)
    key_set = bool(
        stored.get("ai_api_key")
        or (req.ai_provider == "anthropic" and settings.anthropic_api_key)
    )
    return {
        "ai_provider": stored["ai_provider"],
        "ai_model": stored.get("ai_model", settings.ai_model),
        "ai_api_key_set": key_set,
        "ai_base_url": stored.get("ai_base_url", ""),
    }


# ---------------------------------------------------------------------------
# Admin — user management
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Literal["admin", "member", "guest"] = "member"


class UpdateRoleRequest(BaseModel):
    role: Literal["admin", "member", "guest"]


@router.post("/admin/users", status_code=201)
def admin_create_user(req: CreateUserRequest, current_user: dict = Depends(require_admin)):
    try:
        user = auth_service.create_user(req.email, req.password, req.name, role=req.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {k: v for k, v in user.items() if k in {"id", "email", "name", "role", "created_at"}}


@router.get("/admin/users")
def admin_list_users(current_user: dict = Depends(require_admin)):
    return {"users": auth_service.list_users()}


@router.patch("/admin/users/{user_id}")
def admin_update_user_role(
    user_id: str,
    req: UpdateRoleRequest,
    current_user: dict = Depends(require_admin),
):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    try:
        return auth_service.update_user_role(user_id, req.role)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/admin/users/{user_id}", status_code=204)
def admin_delete_user(user_id: str, current_user: dict = Depends(require_admin)):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    try:
        auth_service.delete_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Admin — registration settings
# ---------------------------------------------------------------------------

class AdminSettingsRequest(BaseModel):
    allow_open_registration: bool


@router.get("/admin/settings")
def get_admin_settings(current_user: dict = Depends(require_admin)):
    runtime = auth_service.get_system_settings()
    return {
        "allow_open_registration": runtime.get(
            "allow_open_registration", settings.allow_open_registration
        )
    }


@router.patch("/admin/settings")
def update_admin_settings(
    req: AdminSettingsRequest,
    current_user: dict = Depends(require_admin),
):
    updated = auth_service.update_system_settings(req.model_dump())
    return {"allow_open_registration": updated.get("allow_open_registration")}
