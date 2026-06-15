"""User authentication — JWT tokens, password hashing, user registry."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings
from services.file_service import brain_path

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

AUTH_FILE = brain_path().parent / "auth.json"  # sits alongside brain/, not inside it


def _load_auth() -> dict:
    if not AUTH_FILE.exists():
        return {"users": []}
    with open(AUTH_FILE) as f:
        return json.load(f)


def _save_auth(data: dict) -> None:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUTH_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_user_by_email(email: str) -> dict | None:
    return next(
        (u for u in _load_auth()["users"] if u["email"].lower() == email.lower()), None
    )


def get_user_by_id(user_id: str) -> dict | None:
    return next((u for u in _load_auth()["users"] if u["id"] == user_id), None)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_user(email: str, password: str, name: str, role: str = "member") -> dict:
    import uuid
    data = _load_auth()
    if get_user_by_email(email):
        raise ValueError("Email already registered")
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": name,
        "role": role,  # admin | member | guest
        "hashed_password": hash_password(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data["users"].append(user)
    _save_auth(data)
    return user


def authenticate(email: str, password: str) -> dict | None:
    user = get_user_by_email(email)
    if not user or not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_token(user: dict) -> str:
    payload = {
        "sub": user["id"],
        "name": user["name"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
