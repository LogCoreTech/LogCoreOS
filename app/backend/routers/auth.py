import logging
import re
import secrets
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
from services import auth_service, automations_config, user_deletion_service
from services.features_service import get_effective_disabled
from services.file_service import brain_path, read_json, user_path, write_json
from services.hosting_service import effective_cookie_secure
from services.rate_limiter import rate_limit

router = APIRouter()
bearer_optional = HTTPBearer(auto_error=False)
logger = logging.getLogger("logcore.auth")

_COOKIE = "lc_token"

# Rate limits
_login_limit = rate_limit(
    5, 300, bucket="auth-login"
)  # 5 credential checks / 5 min, shared by /login + /token
_register_limit = rate_limit(3, 3600)  # 3 registrations per hour
_demo_login_limit = rate_limit(5, 3600)  # 5 one-click demo accounts per hour per IP
_me_limit = rate_limit(10, 60)  # 10 profile updates per minute
_get_me_limit = rate_limit(30, 60)  # 30 GET /me or /today per minute (polled endpoints)
_status_limit = rate_limit(20, 60)  # 20 /status checks per minute (public)
_admin_limit = rate_limit(20, 60)  # 20 admin ops per minute


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=1, max_length=60)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class DemoLoginRequest(BaseModel):
    # Browser-detected IANA zone (frontend's own _detectTz() helper) — best-effort,
    # falls back to UTC. Never validated against the real zone list here; setup_user()
    # already does that and a demo account isn't worth a second check for.
    timezone: str = "UTC"


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


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_optional),
    x_workspace: str = Header(default="personal"),
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
    workspace = x_workspace if x_workspace in ("personal", "business") else "personal"
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
    # Coerce a disabled/invalid OR not-entitled active workspace to an enabled
    # one before use — the X-Workspace header is caller-supplied and must
    # never be trusted past what this user's own `workspaces` actually grants.
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


def get_workspace(current_user: dict = Depends(get_current_user)) -> str:
    """The current request's workspace, already validated in get_current_user()
    against this user's own `workspaces` entitlement — every router depends on
    this (never the raw header) so that entitlement check applies everywhere."""
    return current_user["_workspace"]


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
    """Public endpoint — lets the login page (and the app shell) know if
    self-registration is open and whether this is a public demo instance."""
    runtime = auth_service.get_system_settings()
    allow = runtime.get("allow_open_registration", settings.allow_open_registration)
    return {
        "registration_open": auth_service.user_count() == 0 or allow,
        "demo_mode": settings.demo_mode,
    }


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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if is_first_user:
        auth_service.update_user(user["id"], {"workspaces": ["personal", "business"]})
        user["workspaces"] = ["personal", "business"]
    token = auth_service.create_token(user)
    _set_auth_cookie(response, token, auth_service.get_effective_session_minutes())
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


_DEMO_ADJECTIVES = [
    "Swift",
    "Curious",
    "Bright",
    "Quiet",
    "Bold",
    "Clever",
    "Gentle",
    "Sunny",
    "Wandering",
    "Steady",
    "Nimble",
    "Calm",
]
_DEMO_NOUNS = [
    "Otter",
    "Falcon",
    "Fox",
    "Heron",
    "Wolf",
    "Sparrow",
    "Badger",
    "Lynx",
    "Raven",
    "Hare",
    "Finch",
    "Marten",
]
# Mirrors pages/Setup.jsx's own BASE_CATEGORIES exactly — a demo account skips
# the setup wizard entirely, so it needs the same default a real user would
# have picked there, not an invented alternative.
_DEMO_PRIORITIES = ["Religion", "Family", "Job", "Personal Growth", "Hobbies"]


@router.post("/demo-login")
def demo_login(req: DemoLoginRequest, response: Response, _rl: None = Depends(_demo_login_limit)):
    """One-click account for a public demo instance — no email/password/setup wizard.
    Asking a curious visitor to fill out a registration form before they've seen
    anything is exactly the friction a demo exists to remove.

    Only available when DEMO_MODE is on — a personal/managed instance always 404s
    here, the same safety posture demo_reset.py takes for its own destructive
    counterpart (both gate on the instance-level flag, never a per-request check
    a caller could influence). Rate-limited same as /register; a demo account's
    own blast radius is bounded further by the nightly reset wiping it anyway.
    """
    if not settings.demo_mode:
        raise HTTPException(status_code=404)

    name = f"{secrets.choice(_DEMO_ADJECTIVES)} {secrets.choice(_DEMO_NOUNS)}"
    # Never surfaced anywhere — the auth cookie set below is this account's only
    # credential. A demo visitor has no password to remember or lose.
    email = f"demo-{secrets.token_hex(6)}@demo.logcoretech.invalid"
    password = secrets.token_urlsafe(24)

    try:
        user = auth_service.create_user(email, password, name, role="member", timezone=req.timezone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = auth_service.create_token(user)
    _set_auth_cookie(response, token, auth_service.get_effective_session_minutes())

    # Provision the Brain folder directly with the same defaults a real user
    # would pick in the wizard — reuses setup_user() itself rather than
    # duplicating its template-copy/self-contact/features-init logic.
    from routers.setup import SetupRequest, setup_user

    setup_user(
        SetupRequest(priority_order=_DEMO_PRIORITIES, timezone=req.timezone, profile="personal"),
        current_user=user,
    )

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
    _set_auth_cookie(response, token, auth_service.get_effective_session_minutes())
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
    default_dashboard_id: dict | None = None  # {"personal": id|None, "business": id|None}


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
        "notification_channel": current_user.get("notification_channel", ""),
        "channel_rotated_at": current_user.get("channel_rotated_at"),
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
    }


@router.post("/me/rotate-channel")
def rotate_channel(
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_me_limit),
):
    """Regenerate the caller's ntfy channel — the old ID stops receiving immediately."""
    user = auth_service.rotate_notification_channel(current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "ok": True,
        "notification_channel": user["notification_channel"],
        "channel_rotated_at": user["channel_rotated_at"],
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


from services.features_service import all_module_ids as _all_module_ids

_VALID_WORKSPACES = {"personal", "business"}


class ModuleAccessRequest(BaseModel):
    disabled_modules: list[str]

    @field_validator("disabled_modules")
    @classmethod
    def validate_module_ids(cls, v: list[str]) -> list[str]:
        # Computed fresh, not cached at import time — must reflect live
        # install state, same reasoning as all_module_ids() itself.
        invalid = [m for m in v if m not in set(_all_module_ids())]
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
        invalid = [m for m in v if m not in set(_all_module_ids())]
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
# Admin — automation token (n8n -> LogCore write API)
#
# Deliberately lives here, not inside module_packages/assets/backend/router.py
# (where these two endpoints originally lived, before assets/ converted
# 2026-08-27) — the token itself (automations_config.py) is core and shared
# by BOTH Assets' and Contacts' own automation APIs, and this is the ONLY
# admin-facing way to view/rotate it (Hosting.jsx's n8n card calls it
# directly). Leaving it inside Assets' own router would mean uninstalling
# Assets (optional, not locked) silently took away the admin's only way to
# manage a token Contacts' automation API still depends on — found during
# Assets' own conversion research, fixed as part of it rather than carried
# forward silently, matching this project's own standing rule for exactly
# this class of gap.
# ---------------------------------------------------------------------------

_automation_token_limit = rate_limit(30, 60)


@router.get("/admin/automation-token")
def get_automation_token(current_user: dict = Depends(require_admin)):
    return {"token": automations_config.get_api_token()}


@router.post("/admin/automation-token/rotate")
def rotate_automation_token(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_automation_token_limit),
):
    return {"token": automations_config.rotate_api_token()}


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
    # Link this new account to an EXISTING household-pool contact instead of
    # lazily auto-creating a fresh self-contact on first /contacts/me visit —
    # creation-only, no other entry point retroactively links one (owner item
    # #4). Must not already be self_of someone else ("can't reuse an
    # in-use contact"). See routers/contacts.py's GET /available-for-linking.
    contact_id: str | None = None


class UpdateRoleRequest(BaseModel):
    role: Literal["admin", "member", "guest"]


@router.post("/admin/users", status_code=201)
def admin_create_user(req: CreateUserRequest, current_user: dict = Depends(require_admin)):
    from services import contacts_service

    if req.contact_id:
        # Fail-fast pre-check so a bad contact_id never creates an account at
        # all — the authoritative check (same two conditions, race-safe) runs
        # again inside link_self_contact() itself once the account exists.
        candidate = contacts_service.get_contact(
            contacts_service.POOL_HOUSEHOLD, "personal", req.contact_id
        )
        if candidate is None:
            raise HTTPException(status_code=400, detail="Selected contact not found")
        if candidate.get("self_of"):
            raise HTTPException(
                status_code=400,
                detail=f"That contact is already linked to {candidate['self_of']}'s account",
            )

    try:
        user = auth_service.create_user(req.email, req.password, req.name, role=req.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if req.contact_id:
        try:
            contacts_service.link_self_contact(req.contact_id, user["name"])
        except ValueError:
            # Exceedingly rare race (another admin linked the same contact in
            # the instant between the pre-check above and here) — the account
            # itself was already legitimately created, so don't fail the
            # whole request over it. The new user gets an ordinary
            # freshly-created self-contact on their first /contacts/me visit
            # instead, same as if contact_id had never been provided.
            logger.warning(
                "admin_create_user: link_self_contact race for contact_id=%r, user=%r",
                req.contact_id,
                user["name"],
                exc_info=True,
            )

    updates: dict = {}
    feature_role = (req.feature_role or "").strip().lower()
    if feature_role and feature_role != "guest":
        updates["feature_role"] = feature_role
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
    preview = user_deletion_service.build_preview(target)
    if preview["eligible_items"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "This user owns items already shared with someone — use "
                "GET/POST .../deletion-preview and .../deletion-execute to resolve them first."
            ),
        )
    auth_service.delete_user(user_id)
    brain_dir = user_path(target["name"])
    if brain_dir.exists():
        shutil.rmtree(brain_dir)


class DeletionDecision(BaseModel):
    module: Literal["assets", "finance", "contacts", "notes"]
    workspace: Literal["personal", "business"]
    item_id: str
    action: Literal["transfer_user", "transfer_pool", "delete"]
    target_user_id: str | None = None


class DeletionExecuteRequest(BaseModel):
    decisions: list[DeletionDecision] = Field(default_factory=list, max_length=500)


@router.get("/admin/users/{user_id}/deletion-preview")
def admin_user_deletion_preview(user_id: str, current_user: dict = Depends(require_admin)):
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    return user_deletion_service.build_preview(target)


@router.post("/admin/users/{user_id}/deletion-execute")
def admin_user_deletion_execute(
    user_id: str,
    req: DeletionExecuteRequest,
    current_user: dict = Depends(require_admin),
):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        user_deletion_service.execute(
            target,
            [d.model_dump() for d in req.decisions],
            executed_by=current_user["name"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin — registration settings
# ---------------------------------------------------------------------------


class AdminSettingsRequest(BaseModel):
    allow_open_registration: bool | None = None
    enabled_workspaces: list[str] | None = None
    session_minutes: int | None = Field(default=None, ge=60, le=129600)

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
        "session_minutes": auth_service.get_effective_session_minutes(),
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
        "session_minutes": auth_service.get_effective_session_minutes(),
    }
