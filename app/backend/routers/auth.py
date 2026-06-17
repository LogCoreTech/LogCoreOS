from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

from config import settings
from services import auth_service
from services.rate_limiter import rate_limit

router = APIRouter()
bearer = HTTPBearer()
bearer_optional = HTTPBearer(auto_error=False)

# Rate limits: 5 login attempts per 5 min, 3 register per hour
_login_limit    = rate_limit(5, 300)
_register_limit = rate_limit(3, 3600)


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


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    payload = auth_service.decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = auth_service.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    # Attach jti to user dict so logout can revoke it
    user["_jti"] = payload.get("jti")
    return user


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


@router.get("/status")
def registration_status():
    """Public endpoint — lets the login page know if self-registration is available."""
    # Runtime setting in auth.json takes precedence over the env var
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
    credentials: HTTPAuthorizationCredentials = Depends(bearer_optional),
    _rl: None = Depends(_register_limit),
):
    is_first_user = auth_service.user_count() == 0

    if not is_first_user and not settings.allow_open_registration:
        if not credentials:
            raise HTTPException(status_code=403, detail="Registration is closed. An admin must add new users.")
        payload = auth_service.decode_token(credentials.credentials)
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
    return {"token": token, "name": user["name"], "role": user["role"]}


@router.post("/login")
def login(req: LoginRequest, _rl: None = Depends(_login_limit)):
    user = auth_service.authenticate(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth_service.create_token(user)
    return {"token": token, "name": user["name"], "role": user["role"]}


@router.post("/logout")
def logout(current_user: dict = Depends(get_current_user)):
    jti = current_user.get("_jti")
    if jti:
        auth_service.revoke_token(jti)
    return {"ok": True}


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


class ModuleAccessRequest(BaseModel):
    disabled_modules: list[str]


@router.patch("/users/{user_id}/modules")
def update_user_modules(
    user_id: str,
    req: ModuleAccessRequest,
    current_user: dict = Depends(require_admin),
):
    """Set which modules are disabled for a given user (admin only)."""
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Admins cannot restrict their own module access")
    user = auth_service.update_user(user_id, {"disabled_modules": req.disabled_modules})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "disabled_modules": req.disabled_modules}


@router.patch("/session")
def update_session(req: SessionRequest, current_user: dict = Depends(get_current_user)):
    """Update session length for the current user."""
    auth_service.update_user(current_user["id"], {"session_minutes": req.session_minutes})
    return {"ok": True, "session_minutes": req.session_minutes}


@router.get("/today")
def get_today(current_user: dict = Depends(get_current_user)):
    """Return today's date in the user's local timezone (YYYY-MM-DD)."""
    return {"today": auth_service.today_for_user(current_user["name"]).isoformat()}
