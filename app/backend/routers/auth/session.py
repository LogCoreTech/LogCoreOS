"""Login/logout/register/token/status/demo-login — the unauthenticated (or
self-authenticating) session-lifecycle endpoints, split out of the old
routers/auth.py. See routers/auth/__init__.py's docstring for the full
rationale of this package split."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field

from config import settings
from services import auth_service
from services.features_service import get_effective_disabled
from services.rate_limiter import rate_limit

from .deps import _COOKIE, _clear_auth_cookie, _set_auth_cookie, bearer_optional, get_current_user

router = APIRouter()

# Rate limits
_login_limit = rate_limit(
    5, 300, bucket="auth-login"
)  # 5 credential checks / 5 min, shared by /login + /token
_register_limit = rate_limit(3, 3600)  # 3 registrations per hour
_demo_login_limit = rate_limit(5, 3600)  # 5 one-click demo accounts per hour per IP
_status_limit = rate_limit(20, 60)  # 20 /status checks per minute (public)


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
        # Never trust the token's own embedded `role` claim here — nothing revokes a
        # token on role change or account deletion (only logout() does), so a demoted
        # or deleted admin's still-unexpired token would otherwise keep this endpoint
        # open indefinitely (found 2026-09-07). Re-fetch the user fresh from disk, the
        # same way get_current_user()/require_admin do for every other admin-gated path.
        payload = auth_service.decode_token(admin_token)
        admin_user = auth_service.get_user_by_id(payload["sub"]) if payload else None
        if not admin_user or admin_user.get("role") != "admin":
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
