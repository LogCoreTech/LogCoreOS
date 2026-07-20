import re
import shutil
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator

from config import settings
from services import auth_service
from services.features_service import get_effective_disabled
from services.file_service import brain_path, read_json, user_path, write_json
from services.hosting_service import effective_cookie_secure
from services.rate_limiter import rate_limit

router = APIRouter()
bearer_optional = HTTPBearer(auto_error=False)

_COOKIE = "lc_token"

# Rate limits
_login_limit = rate_limit(5, 300, bucket="auth-login")  # 5 credential checks / 5 min, shared by /login + /token
_register_limit = rate_limit(3, 3600)  # 3 registrations per hour
_me_limit = rate_limit(10, 60)  # 10 profile updates per minute
_get_me_limit = rate_limit(30, 60)  # 30 GET /me or /today per minute (polled endpoints)
_status_limit = rate_limit(20, 60)  # 20 /status checks per minute (public)
_admin_limit = rate_limit(20, 60)  # 20 admin ops per minute


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
        secure=effective_cookie_secure(),
        samesite="lax",
        max_age=session_minutes * 60,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=_COOKIE, path="/", samesite="lax")


def get_workspace(x_workspace: str = Header(default="personal")) -> str:
    """Read the X-Workspace header and return a validated workspace name."""
    return x_workspace if x_workspace in ("personal", "business") else "personal"


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_optional),
    workspace: str = Depends(get_workspace),
) -> dict:
    # Accept httpOnly cookie first, then fall back to Authorization header
    token = request.cookies.get(_COOKIE)
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = auth_service.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    user = auth_service.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    # Attach jti and exp so logout can revoke with persistence
    user["_jti"] = payload.get("jti")
    user["_exp"] = payload.get("exp")
    enabled_ws = auth_service.enabled_workspaces()
    # Lazy migration: admins get every instance-enabled workspace (persisted so
    # access is restored automatically if a hidden workspace is re-enabled).
    if user.get("role") == "admin":
        want = [w for w in ("personal", "business") if w in enabled_ws]
        have = user.get("workspaces", [])
        if not set(want).issubset(set(have)):
            merged = sorted(set(have) | set(want))
            auth_service.update_user(user["id"], {"workspaces": merged})
            user["workspaces"] = merged
    # Hide instance-disabled workspaces from what the frontend sees (never empty).
    effective_ws = [w for w in user.get("workspaces", ["personal"]) if w in enabled_ws]
    if not effective_ws:
        effective_ws = [enabled_ws[0]]
    user["workspaces"] = effective_ws
    # Coerce a disabled/invalid active workspace to an enabled one before use.
    if workspace not in effective_ws:
        workspace = effective_ws[0]
    # Compute effective disabled modules for the current workspace
    user["disabled_modules"] = get_effective_disabled(
        user.get("feature_role", "member"),
        user.get("disabled_modules", []),
        workspace,
    )
    user["_workspace"] = workspace
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


def require_pool_edit(pool: str):
    """Dependency factory for pool (household/team) write access.

    Admins always pass. Otherwise the user must have been granted management
    rights for this pool — i.e. `pool` is in their per-user `pool_edit` list.
    Grants full pool-manager parity (add/edit/delete events + tasks + assign).
    A grant is default-off, so this cannot use the disabled_modules union model
    (which only ever adds restrictions); it is a dedicated per-user grant.
    """

    def check(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") == "admin":
            return current_user
        if pool in (current_user.get("pool_edit") or []):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to make changes here.",
        )

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
            raise HTTPException(
                status_code=403, detail="Registration is closed. An admin must add new users."
            )
        payload = auth_service.decode_token(admin_token)
        if not payload or payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins can register new users.")

    role = "admin" if is_first_user else "member"
    try:
        user = auth_service.create_user(
            req.email,
            req.password,
            req.name,
            role=role,
            session_minutes=req.session_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if is_first_user:
        auth_service.update_user(user["id"], {"workspaces": ["personal", "business"]})
        user["workspaces"] = ["personal", "business"]
    token = auth_service.create_token(user)
    _set_auth_cookie(response, token, user.get("session_minutes", 10080))
    effective = get_effective_disabled(
        user.get("feature_role", "member"),
        user.get("disabled_modules", []),
        "personal",
    )
    return {
        "id": user["id"],
        "name": user["name"],
        "role": user["role"],
        "disabled_modules": effective,
        "workspaces": user.get("workspaces", ["personal"]),
        "timezone": user.get("timezone", "UTC"),
        "accent_color": user.get("accent_color"),
        "dark_mode": user.get("dark_mode", "system"),
        "background": user.get("background"),
        "density": user.get("density", "comfortable"),
        "corner_style": user.get("corner_style", "rounded"),
    }


@router.post("/login")
def login(req: LoginRequest, response: Response, _rl: None = Depends(_login_limit)):
    user, locked = auth_service.login_attempt(req.email, req.password)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {locked} seconds.",
        )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth_service.create_token(user)
    _set_auth_cookie(response, token, user.get("session_minutes", 10080))
    effective = get_effective_disabled(
        user.get("feature_role", "member"),
        user.get("disabled_modules", []),
        "personal",
    )
    return {
        "id": user["id"],
        "name": user["name"],
        "role": user["role"],
        "disabled_modules": effective,
        "workspaces": user.get("workspaces", ["personal"]),
        "timezone": user.get("timezone", "UTC"),
        "accent_color": user.get("accent_color"),
        "dark_mode": user.get("dark_mode", "system"),
        "background": user.get("background"),
        "density": user.get("density", "comfortable"),
        "corner_style": user.get("corner_style", "rounded"),
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
def get_token(req: LoginRequest, _rl: None = Depends(_login_limit)):
    """Return a plain Bearer token for CLI / programmatic clients.
    Browser sessions should use /login (sets HttpOnly cookie instead)."""
    user, locked = auth_service.login_attempt(req.email, req.password)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {locked} seconds.",
        )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"token": auth_service.create_token(user)}


def _validate_timezone(tz: str) -> str:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, Exception):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timezone: '{tz}'. Use an IANA zone name like 'America/Chicago'.",
        )
    return tz


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
        "notification_channel": current_user.get("notification_channel", ""),
        "session_minutes": current_user.get("session_minutes", 10080),
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


@router.get("/users")
def list_users_legacy(current_user: dict = Depends(require_admin)):
    """List all users without sensitive fields (admin only)."""
    data = auth_service._load_auth()
    safe_fields = {"id", "name", "email", "role", "timezone", "disabled_modules", "created_at"}
    return [{k: v for k, v in u.items() if k in safe_fields} for u in data["users"]]


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


from services.features_service import ALL_MODULE_IDS as _ALL_MODULE_IDS

VALID_MODULE_IDS = set(_ALL_MODULE_IDS)

_VALID_WORKSPACES = {"personal", "business"}


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
        raise HTTPException(
            status_code=400, detail="Admins cannot restrict their own module access"
        )
    user = auth_service.update_user(user_id, {"disabled_modules": req.disabled_modules})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "disabled_modules": req.disabled_modules}


class WorkspacesRequest(BaseModel):
    workspaces: list[str]

    @field_validator("workspaces")
    @classmethod
    def validate_workspaces(cls, v: list[str]) -> list[str]:
        invalid = [w for w in v if w not in _VALID_WORKSPACES]
        if invalid:
            raise ValueError(f"Unknown workspaces: {invalid}")
        if not v:
            raise ValueError("At least one workspace is required")
        return v


@router.patch("/admin/users/{user_id}/workspaces")
def update_user_workspaces(
    user_id: str,
    req: WorkspacesRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Set which workspaces a user can access (admin only)."""
    disabled = [w for w in req.workspaces if w not in auth_service.enabled_workspaces()]
    if disabled:
        raise HTTPException(
            status_code=400,
            detail=f"Workspace(s) disabled for this instance: {disabled}",
        )
    user = auth_service.update_user(user_id, {"workspaces": req.workspaces})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "workspaces": req.workspaces}


_VALID_POOLS = {"household", "team"}


class PoolEditRequest(BaseModel):
    pool_edit: list[str]

    @field_validator("pool_edit")
    @classmethod
    def validate_pools(cls, v: list[str]) -> list[str]:
        invalid = [p for p in v if p not in _VALID_POOLS]
        if invalid:
            raise ValueError(f"Unknown pool(s): {invalid}")
        return sorted(set(v))


@router.patch("/admin/users/{user_id}/pool-edit")
def update_user_pool_edit(
    user_id: str,
    req: PoolEditRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Grant/revoke household & team pool-management rights for a user (admin only)."""
    user = auth_service.update_user(user_id, {"pool_edit": req.pool_edit})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "pool_edit": req.pool_edit}


class WorkspaceModulesRequest(BaseModel):
    workspace: str
    disabled_modules: list[str]

    @field_validator("workspace")
    @classmethod
    def validate_ws(cls, v: str) -> str:
        if v not in _VALID_WORKSPACES:
            raise ValueError(f"workspace must be one of: {_VALID_WORKSPACES}")
        return v

    @field_validator("disabled_modules")
    @classmethod
    def validate_mods(cls, v: list[str]) -> list[str]:
        invalid = [m for m in v if m not in VALID_MODULE_IDS]
        if invalid:
            raise ValueError(f"Unknown module IDs: {invalid}")
        return v


@router.patch("/admin/users/{user_id}/workspace-modules")
def update_workspace_modules(
    user_id: str,
    req: WorkspaceModulesRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Set disabled modules for a specific workspace for a user (admin only)."""
    if user_id == current_user["id"]:
        raise HTTPException(
            status_code=400, detail="Admins cannot restrict their own module access"
        )
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    raw = target.get("disabled_modules", {})
    if isinstance(raw, list):
        raw = {"personal": raw, "business": raw}
    raw[req.workspace] = req.disabled_modules
    auth_service.update_user(user_id, {"disabled_modules": raw})
    return {"ok": True, "workspace": req.workspace, "disabled_modules": req.disabled_modules}


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


_session_limit = rate_limit(5, 3600)  # 5 session updates per hour


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
        stored.get("ai_api_key") or (provider == "anthropic" and settings.anthropic_api_key)
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
        stored.get("ai_api_key") or (req.ai_provider == "anthropic" and settings.anthropic_api_key)
    )
    return {
        "ai_provider": stored["ai_provider"],
        "ai_model": stored.get("ai_model", settings.ai_model),
        "ai_api_key_set": key_set,
        "ai_base_url": stored.get("ai_base_url", ""),
    }


class SearchSettingsRequest(BaseModel):
    tavily_api_key: str = ""


@router.get("/admin/search-settings")
def get_search_settings(current_user: dict = Depends(require_admin)):
    stored = read_json(_AI_SETTINGS_PATH, default={})
    key_set = bool(stored.get("tavily_api_key") or settings.tavily_api_key)
    return {"tavily_key_set": key_set}


@router.patch("/admin/search-settings")
def update_search_settings(
    req: SearchSettingsRequest,
    current_user: dict = Depends(require_admin),
):
    stored = read_json(_AI_SETTINGS_PATH, default={})
    if req.tavily_api_key:
        stored["tavily_api_key"] = req.tavily_api_key
    write_json(_AI_SETTINGS_PATH, stored)
    key_set = bool(stored.get("tavily_api_key") or settings.tavily_api_key)
    return {"tavily_key_set": key_set}


# ---------------------------------------------------------------------------
# Admin — hosting settings
# ---------------------------------------------------------------------------

_HOSTING_SETTINGS_PATH = brain_path() / "hosting.json"


class HostingSettingsRequest(BaseModel):
    cookie_secure: bool
    trust_proxy_headers: bool
    domain_url: str = ""
    proxy_type: str = ""  # "cloudflare" | "nginx" | ""
    tunnel_token: str = ""  # Cloudflare tunnel token; empty = don't overwrite stored value


@router.get("/admin/hosting-settings")
def get_hosting_settings(current_user: dict = Depends(require_admin)):
    stored = read_json(_HOSTING_SETTINGS_PATH, default={})
    return {
        "cookie_secure": stored.get("cookie_secure", settings.cookie_secure),
        "trust_proxy_headers": stored.get("trust_proxy_headers", settings.trust_proxy_headers),
        "domain_url": stored.get("domain_url", ""),
        "proxy_type": stored.get("proxy_type", ""),
        "tunnel_token_set": bool(stored.get("tunnel_token", "")),
    }


@router.patch("/admin/hosting-settings")
def update_hosting_settings(
    req: HostingSettingsRequest,
    current_user: dict = Depends(require_admin),
):
    stored = read_json(_HOSTING_SETTINGS_PATH, default={})
    stored["cookie_secure"] = req.cookie_secure
    stored["trust_proxy_headers"] = req.trust_proxy_headers
    stored["domain_url"] = req.domain_url.rstrip("/")
    stored["proxy_type"] = req.proxy_type
    if req.tunnel_token:
        stored["tunnel_token"] = req.tunnel_token
    write_json(_HOSTING_SETTINGS_PATH, stored)
    return {
        "cookie_secure": stored["cookie_secure"],
        "trust_proxy_headers": stored["trust_proxy_headers"],
        "domain_url": stored["domain_url"],
        "proxy_type": stored["proxy_type"],
        "tunnel_token_set": bool(stored.get("tunnel_token", "")),
    }


@router.post("/admin/hosting-settings/apply")
def apply_hosting_settings(current_user: dict = Depends(require_admin)):
    stored = read_json(_HOSTING_SETTINGS_PATH, default={})
    if stored.get("proxy_type") != "cloudflare":
        raise HTTPException(
            status_code=400, detail="Apply is only available for Cloudflare Tunnel mode."
        )
    token = stored.get("tunnel_token", "")
    if not token:
        raise HTTPException(status_code=400, detail="No tunnel token saved. Save settings first.")
    try:
        import docker as docker_sdk

        client = docker_sdk.from_env()
        # Stop and remove the existing container so we can recreate it with the current token.
        # A plain restart keeps the original env vars from container creation time.
        try:
            old = client.containers.get("logcore-tunnel")
            old.stop(timeout=10)
            old.remove()
        except docker_sdk.errors.NotFound:
            pass
        client.containers.run(
            "cloudflare/cloudflared:latest",
            command="tunnel --no-autoupdate run",
            name="logcore-tunnel",
            detach=True,
            network_mode="host",
            restart_policy={"Name": "unless-stopped"},
            environment={"TUNNEL_TOKEN": token},
        )
    except docker_sdk.errors.DockerException as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Admin — user management
# ---------------------------------------------------------------------------


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Literal["admin", "member", "guest"] = "member"
    feature_role: str = "guest"
    workspaces: list[str] = ["personal"]


class UpdateRoleRequest(BaseModel):
    role: Literal["admin", "member", "guest"]


@router.post("/admin/users", status_code=201)
def admin_create_user(req: CreateUserRequest, current_user: dict = Depends(require_admin)):
    try:
        user = auth_service.create_user(req.email, req.password, req.name, role=req.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    updates: dict = {}
    if req.feature_role and req.feature_role != "guest":
        updates["feature_role"] = req.feature_role
    valid_ws = [w for w in req.workspaces if w in ("personal", "business")]
    if valid_ws:
        updates["workspaces"] = valid_ws
    if updates:
        auth_service.update_user(user["id"], updates)
    return {k: v for k, v in user.items() if k in {"id", "email", "name", "role", "created_at"}}


_ADMIN_USER_FIELDS = {
    "id",
    "email",
    "name",
    "role",
    "created_at",
    "feature_role",
    "disabled_modules",
    "workspaces",
    "pool_edit",
    "timezone",
}


@router.get("/admin/users")
def admin_list_users(current_user: dict = Depends(require_admin)):
    data = auth_service._load_auth()
    users = [{k: v for k, v in u.items() if k in _ADMIN_USER_FIELDS} for u in data.get("users", [])]
    return {"users": users}


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
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    auth_service.delete_user(user_id)
    brain_dir = user_path(target["name"])
    if brain_dir.exists():
        shutil.rmtree(brain_dir)


# ---------------------------------------------------------------------------
# Admin — registration settings
# ---------------------------------------------------------------------------


class AdminSettingsRequest(BaseModel):
    allow_open_registration: bool | None = None
    enabled_workspaces: list[str] | None = None

    @field_validator("enabled_workspaces")
    @classmethod
    def _validate_workspaces(cls, v):
        if v is None:
            return v
        invalid = [w for w in v if w not in _VALID_WORKSPACES]
        if invalid:
            raise ValueError(f"Invalid workspace(s): {invalid}")
        if not v:
            raise ValueError("At least one workspace must remain enabled")
        return v


@router.get("/admin/settings")
def get_admin_settings(current_user: dict = Depends(require_admin)):
    runtime = auth_service.get_system_settings()
    return {
        "allow_open_registration": runtime.get(
            "allow_open_registration", settings.allow_open_registration
        ),
        "enabled_workspaces": auth_service.enabled_workspaces(),
    }


@router.patch("/admin/settings")
def update_admin_settings(
    req: AdminSettingsRequest,
    current_user: dict = Depends(require_admin),
):
    updated = auth_service.update_system_settings(req.model_dump(exclude_none=True))
    return {
        "allow_open_registration": updated.get("allow_open_registration"),
        "enabled_workspaces": auth_service.enabled_workspaces(),
    }
