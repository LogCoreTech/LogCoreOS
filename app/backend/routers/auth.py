from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

from config import settings
from services import auth_service
from services.file_service import brain_path, read_json, write_json

router = APIRouter()

# auto_error=False so the dependency returns None instead of 401 when the
# Authorization header is absent — lets us check the cookie first.
_bearer = HTTPBearer(auto_error=False)
_COOKIE = "lc_token"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    # Cookie takes priority; Bearer header is the fallback for CLI / API clients.
    token = request.cookies.get(_COOKIE)
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = auth_service.decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = auth_service.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


_ADMIN_SETTINGS_PATH = brain_path() / "admin_settings.json"


def _get_admin_settings() -> dict:
    return read_json(_ADMIN_SETTINGS_PATH, default={"allow_registration": settings.allow_open_registration})


@router.post("/register")
def register(req: RegisterRequest, response: Response):
    if not _get_admin_settings().get("allow_registration", False):
        raise HTTPException(status_code=403, detail="Registration is closed")
    try:
        user = auth_service.create_user(req.email, req.password, req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _set_auth_cookie(response, auth_service.create_token(user))
    return {"id": user["id"], "name": user["name"], "role": user["role"]}


@router.post("/login")
def login(req: LoginRequest, response: Response):
    user = auth_service.authenticate(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    _set_auth_cookie(response, auth_service.create_token(user))
    return {"id": user["id"], "name": user["name"], "role": user["role"]}


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(key=_COOKIE, path="/")


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return {"id": current_user["id"], "name": current_user["name"], "role": current_user["role"]}


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
def list_users(current_user: dict = Depends(require_admin)):
    return {"users": auth_service.list_users()}


@router.patch("/admin/users/{user_id}")
def update_user_role(
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
def delete_user(user_id: str, current_user: dict = Depends(require_admin)):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    try:
        auth_service.delete_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Admin — registration settings
# ---------------------------------------------------------------------------

class RegistrationSettingsRequest(BaseModel):
    allow_registration: bool


@router.get("/admin/settings")
def get_admin_settings(current_user: dict = Depends(require_admin)):
    return _get_admin_settings()


@router.patch("/admin/settings")
def update_admin_settings(
    req: RegistrationSettingsRequest,
    current_user: dict = Depends(require_admin),
):
    stored = _get_admin_settings()
    stored["allow_registration"] = req.allow_registration
    write_json(_ADMIN_SETTINGS_PATH, stored)
    return stored
