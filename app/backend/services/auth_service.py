"""User authentication — JWT tokens, password hashing, user registry."""
import json
import logging
import re
import threading
import uuid as uuid_module
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings
from services.file_service import brain_path, write_json

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)


def _auth_path() -> Path:
    """Auth data lives inside brain/_system/ so it's covered by the brain volume mount."""
    p = brain_path() / "_system" / "auth.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# In-memory token blacklist — bootstrapped from disk at startup
_revoked_jtis: set[str] = set()
_revoked_lock = threading.Lock()

# Allowed characters in user names — prevents path traversal
_NAME_RE = re.compile(r"^(?=.*[A-Za-z0-9])[A-Za-z0-9 '_\-]{1,60}$")


def _load_auth() -> dict:
    path = _auth_path()
    if not path.exists():
        return {"users": []}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("auth.json is corrupt or unreadable: %s", exc)
        return {"users": []}


def _save_auth(data: dict) -> None:
    """Atomically write auth.json — prevents corruption on crash mid-write."""
    write_json(_auth_path(), data)


def _bootstrap_revoked_jtis() -> None:
    """Reload persisted revoked JTIs from disk into memory after a process restart."""
    try:
        data = _load_auth()
        revoked = data.get("revoked_jtis", {})
        now = datetime.now(timezone.utc)
        for jti, exp_str in revoked.items():
            try:
                if datetime.fromisoformat(exp_str) > now:
                    _revoked_jtis.add(jti)
            except (ValueError, TypeError):
                pass
    except Exception as exc:
        logger.warning("Could not bootstrap revoked JTIs: %s", exc)


_bootstrap_revoked_jtis()


def user_count() -> int:
    return len(_load_auth()["users"])


def get_user_by_email(email: str) -> dict | None:
    return next(
        (u for u in _load_auth()["users"] if u["email"] == email.lower()), None
    )


def get_user_by_id(user_id: str) -> dict | None:
    return next((u for u in _load_auth()["users"] if u["id"] == user_id), None)


def get_user_by_name(name: str) -> dict | None:
    return next((u for u in _load_auth()["users"] if u["name"] == name), None)


def update_user(user_id: str, updates: dict) -> dict | None:
    data = _load_auth()
    for u in data["users"]:
        if u["id"] == user_id:
            u.update(updates)
            _save_auth(data)
            return u
    return None


def get_system_settings() -> dict:
    """Return the runtime settings block stored in auth.json."""
    return _load_auth().get("settings", {})


def update_system_settings(updates: dict) -> dict:
    """Merge updates into the runtime settings block and persist."""
    data = _load_auth()
    data.setdefault("settings", {}).update(updates)
    _save_auth(data)
    return data["settings"]


def get_user_timezone(user_name: str) -> str:
    user = get_user_by_name(user_name)
    return (user or {}).get("timezone", "UTC")


def today_for_user(user_name: str) -> date:
    """Return today's date in the user's local timezone."""
    tz_str = get_user_timezone(user_name)
    try:
        return datetime.now(ZoneInfo(tz_str)).date()
    except (ZoneInfoNotFoundError, Exception):
        logger.warning(
            "Invalid timezone '%s' for user '%s', falling back to UTC",
            tz_str, user_name,
        )
        return datetime.now(timezone.utc).date()


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_user(
    email: str,
    password: str,
    name: str,
    role: str = "member",
    timezone: str = "UTC",
    session_minutes: int = 10080,
) -> dict:
    # Validate name — prevents path traversal and markdown injection
    if not _NAME_RE.match(name):
        raise ValueError(
            "Name must be 1–60 characters and may only contain letters, numbers, "
            "spaces, apostrophes, hyphens, and underscores."
        )

    normalized_email = email.lower()
    data = _load_auth()
    if get_user_by_email(normalized_email):
        raise ValueError("Email already registered")

    user = {
        "id": str(uuid_module.uuid4()),
        "email": normalized_email,
        "name": name,
        "role": role,
        "hashed_password": hash_password(password),
        "timezone": timezone,
        "session_minutes": session_minutes,
        "notification_channel": f"lc-{uuid_module.uuid4().hex[:12]}",
        "created_at": datetime.now(ZoneInfo("UTC")).isoformat(),
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
    session_minutes = user.get("session_minutes", settings.access_token_expire_minutes)
    payload = {
        "sub": user["id"],
        "jti": str(uuid_module.uuid4()),
        "name": user["name"],
        "role": user["role"],
        "exp": datetime.now(ZoneInfo("UTC")) + timedelta(minutes=session_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        jti = payload.get("jti")
        if jti and is_revoked(jti):
            return None
        return payload
    except JWTError:
        return None


def revoke_token(jti: str, exp: int | None = None) -> None:
    """Revoke a JTI in memory and persist it to disk so it survives restarts."""
    with _revoked_lock:
        _revoked_jtis.add(jti)
    if exp is not None:
        try:
            exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
            data = _load_auth()
            revoked = data.setdefault("revoked_jtis", {})
            revoked[jti] = exp_dt.isoformat()
            # Prune entries whose tokens have already expired — they're harmless anyway
            now = datetime.now(timezone.utc)
            data["revoked_jtis"] = {
                k: v for k, v in revoked.items()
                if datetime.fromisoformat(v) > now
            }
            _save_auth(data)
        except Exception as exc:
            logger.warning("Could not persist revoked JTI %s: %s", jti, exc)


def is_revoked(jti: str) -> bool:
    with _revoked_lock:
        return jti in _revoked_jtis
