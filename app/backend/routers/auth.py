from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

from config import settings
from services import auth_service
from services.file_service import brain_path, read_json, write_json

router = APIRouter()
bearer = HTTPBearer()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    payload = auth_service.decode_token(credentials.credentials)
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


@router.post("/register")
def register(req: RegisterRequest):
    try:
        user = auth_service.create_user(req.email, req.password, req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = auth_service.create_token(user)
    return {"token": token, "name": user["name"], "role": user["role"]}


@router.post("/login")
def login(req: LoginRequest):
    user = auth_service.authenticate(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth_service.create_token(user)
    return {"token": token, "name": user["name"], "role": user["role"]}


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
