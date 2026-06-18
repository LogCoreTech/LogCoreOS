from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import settings
from services import auth_service
from services.rate_limiter import rate_limit

router = APIRouter()
bearer = HTTPBearer()
bearer_optional = HTTPBearer(auto_error=False)

# Rate limits
_login_limit    = rate_limit(5, 300)    # 5 login attempts per 5 min
_register_limit = rate_limit(3, 3600)   # 3 registrations per hour
_me_limit       = rate_limit(10, 60)    # 10 profile updates per minute
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


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_optional),
) -> dict:
    # Accept httpOnly cookie first, then fall back to Authorization header
    token = request.cookies.get("lc_token")
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


def _set_auth_cookie(response: Response, token: str, session_minutes: int) -> None:
    response.set_cookie(
        key="lc_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=session_minutes * 60,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key="lc_token", path="/", samesite="strict")


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
def registration_status():
    """Public endpoint — lets the login page know if self-registration is available."""
    runtime = auth_service.get_system_settings()
    allow = runtime.get("allow_open_registration", settings.allow_open_registration)
    return {"registration_open": auth_service.user_count() == 0 or allow}


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
        admin_token = request.cookies.get("lc_token")
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
        "name": user["name"],
        "role": user["role"],
        "disabled_modules": user.get("disabled_modules", []),
        "timezone": user.get("timezone", "UTC"),
    }


@router.post("/login")
def login(req: LoginRequest, response: Response, _rl: None = Depends(_login_limit)):
    user = auth_service.authenticate(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth_service.create_token(user)
    _set_auth_cookie(response, token, user.get("session_minutes", 10080))
    return {
        "name": user["name"],
        "role": user["role"],
        "disabled_modules": user.get("disabled_modules", []),
        "timezone": user.get("timezone", "UTC"),
    }


@router.post("/logout")
def logout(response: Response, current_user: dict = Depends(get_current_user)):
    jti = current_user.get("_jti")
    exp = current_user.get("_exp")
    if jti:
        auth_service.revoke_token(jti, exp)
    _clear_auth_cookie(response)
    return {"ok": True}


def _validate_timezone(tz: str) -> str:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, Exception):
        raise HTTPException(status_code=400, detail=f"Invalid timezone: '{tz}'. Use an IANA zone name like 'America/Chicago'.")
    return tz


class MeUpdateRequest(BaseModel):
    timezone: str | None = Field(None, max_length=50)


@router.patch("/me")
def update_me(req: MeUpdateRequest, current_user: dict = Depends(get_current_user), _rl: None = Depends(_me_limit)):
    """Update the current user's own profile fields (timezone for now)."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "timezone" in updates:
        _validate_timezone(updates["timezone"])
    if not updates:
        return {"ok": True}
    auth_service.update_user(current_user["id"], updates)
    return {"ok": True, **updates}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "role": current_user["role"],
        "notification_channel": current_user.get("notification_channel", ""),
        "session_minutes": current_user.get("session_minutes", 10080),
        "timezone": current_user.get("timezone", "UTC"),
        "disabled_modules": current_user.get("disabled_modules", []),
    }


@router.get("/users")
def list_users(current_user: dict = Depends(require_admin)):
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
def update_user_role(
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


@router.patch("/session")
def update_session(req: SessionRequest, current_user: dict = Depends(get_current_user)):
    """Update session length for the current user."""
    auth_service.update_user(current_user["id"], {"session_minutes": req.session_minutes})
    return {"ok": True, "session_minutes": req.session_minutes}


@router.get("/today")
def get_today(current_user: dict = Depends(get_current_user)):
    """Return today's date in the user's local timezone (YYYY-MM-DD)."""
    return {"today": auth_service.today_for_user(current_user["name"]).isoformat()}
