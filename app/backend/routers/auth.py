from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

from config import settings
from services import auth_service

router = APIRouter()
bearer = HTTPBearer()
bearer_optional = HTTPBearer(auto_error=False)


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


@router.post("/register")
def register(
    req: RegisterRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_optional),
):
    is_first_user = auth_service.user_count() == 0

    if not is_first_user and not settings.allow_open_registration:
        # Subsequent users must be created by an authenticated admin
        if not credentials:
            raise HTTPException(status_code=403, detail="Registration is closed. An admin must add new users.")
        payload = auth_service.decode_token(credentials.credentials)
        if not payload or payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins can register new users.")

    role = "admin" if is_first_user else "member"
    try:
        user = auth_service.create_user(req.email, req.password, req.name, role=role)
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
