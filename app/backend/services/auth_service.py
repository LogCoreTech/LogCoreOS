"""User authentication — JWT tokens, password hashing, user registry."""

import json
import logging
import re
import threading
import time
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

# A fixed dummy bcrypt hash. When authenticate() is called with an unknown email
# we still run a bcrypt verification against this hash so the response time does
# not reveal whether the email exists (constant-time login — blocks timing-based
# user enumeration). It never matches any real password.
_DUMMY_HASH = pwd_context.hash("logcore-dummy-password-never-matches")

# --- Account-scoped login lockout -------------------------------------------
# The per-IP rate limiter (services/rate_limiter.py) throttles a single source
# address, but does nothing against distributed credential-stuffing where many
# IPs each try a few passwords against ONE account. This adds a per-account
# (email-keyed) sliding-window lockout as a second layer.
#
# It is a *temporary* lock, not a permanent one: after _LOCKOUT_THRESHOLD failed
# attempts inside _LOCKOUT_WINDOW seconds the account is refused until the oldest
# failure ages out of the window, then it auto-recovers. Failures are only
# recorded for genuine bad-credential attempts (the router checks the lock BEFORE
# authenticating, so attempts made while already locked never extend it) — so an
# attacker cannot keep a victim permanently locked out by hammering their email.
# In-memory only (resets on restart), consistent with the rate limiter; safe for
# the single-worker uvicorn deployment.
_LOCKOUT_THRESHOLD = 10
_LOCKOUT_WINDOW = 900  # seconds (15 min)
_failed_logins: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def account_lock_remaining(email: str) -> int:
    """Seconds until the account can be tried again, or 0 if not locked."""
    key = email.lower()
    now = time.monotonic()
    with _login_lock:
        fails = [t for t in _failed_logins.get(key, []) if now - t < _LOCKOUT_WINDOW]
        if fails:
            _failed_logins[key] = fails
        else:
            _failed_logins.pop(key, None)
        if len(fails) >= _LOCKOUT_THRESHOLD:
            return max(1, int(_LOCKOUT_WINDOW - (now - fails[0])))
        return 0


def record_failed_login(email: str) -> None:
    """Record a bad-credential attempt for the account's lockout window."""
    key = email.lower()
    now = time.monotonic()
    with _login_lock:
        fails = [t for t in _failed_logins.get(key, []) if now - t < _LOCKOUT_WINDOW]
        fails.append(now)
        _failed_logins[key] = fails


def clear_failed_login(email: str) -> None:
    """Reset the failure counter after a successful login."""
    with _login_lock:
        _failed_logins.pop(email.lower(), None)


def login_attempt(email: str, password: str) -> tuple[dict | None, int]:
    """Authenticate with account-scoped lockout applied.

    Returns (user, lock_remaining_seconds):
      - lock_remaining > 0 → account temporarily locked; user is None. The caller
        must NOT reveal whether the credentials were valid.
      - user is None, lock 0 → bad credentials (a failure has been recorded).
      - user set → success (the failure counter has been cleared).
    """
    remaining = account_lock_remaining(email)
    if remaining > 0:
        return None, remaining
    user = authenticate(email, password)
    if user is None:
        record_failed_login(email)
        return None, 0
    clear_failed_login(email)
    return user, 0


def _auth_path() -> Path:
    """Auth data lives inside brain/_system/ so it's covered by the brain volume mount."""
    p = brain_path() / "_system" / "auth.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# In-memory token blacklist — bootstrapped from disk at startup
_revoked_jtis: set[str] = set()
_revoked_lock = threading.Lock()

# Serialises all read-modify-write operations on auth.json
_auth_lock = threading.Lock()

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
    return next((u for u in _load_auth()["users"] if u["email"] == email.lower()), None)


def get_user_by_id(user_id: str) -> dict | None:
    return next((u for u in _load_auth()["users"] if u["id"] == user_id), None)


def get_user_by_name(name: str) -> dict | None:
    return next((u for u in _load_auth()["users"] if u["name"] == name), None)


def update_user(user_id: str, updates: dict) -> dict | None:
    with _auth_lock:
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
    with _auth_lock:
        data = _load_auth()
        data.setdefault("settings", {}).update(updates)
        _save_auth(data)
        return data["settings"]


def enabled_workspaces() -> list[str]:
    """Instance-wide list of workspaces available on this install.

    Defaults to both. Always returns at least one valid workspace so an empty
    or malformed setting can never lock everyone out.
    """
    raw = get_system_settings().get("enabled_workspaces")
    valid = [w for w in (raw or []) if w in ("personal", "business")]
    return valid or ["personal", "business"]


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
            tz_str,
            user_name,
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
    with _auth_lock:
        data = _load_auth()
        if any(u["email"] == normalized_email for u in data["users"]):
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


_SAFE_FIELDS = {"id", "email", "name", "role", "created_at"}


def list_users() -> list[dict]:
    return [{k: v for k, v in u.items() if k in _SAFE_FIELDS} for u in _load_auth()["users"]]


def update_user_role(user_id: str, role: str) -> dict:
    data = _load_auth()
    for user in data["users"]:
        if user["id"] == user_id:
            user["role"] = role
            _save_auth(data)
            return {k: v for k, v in user.items() if k in _SAFE_FIELDS}
    raise ValueError("User not found")


def delete_user(user_id: str) -> None:
    data = _load_auth()
    original = len(data["users"])
    data["users"] = [u for u in data["users"] if u["id"] != user_id]
    if len(data["users"]) == original:
        raise ValueError("User not found")
    _save_auth(data)


def authenticate(email: str, password: str) -> dict | None:
    user = get_user_by_email(email)
    # Always run a bcrypt verification — against the real hash if the user exists,
    # otherwise against a fixed dummy hash — so both paths take the same time and
    # an unknown vs. known email can't be distinguished by response latency.
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user["hashed_password"]):
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
        header = jwt.get_unverified_header(token)
        if header.get("alg") != settings.algorithm:
            return None
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
            with _auth_lock:
                data = _load_auth()
                revoked = data.setdefault("revoked_jtis", {})
                revoked[jti] = exp_dt.isoformat()
                now = datetime.now(timezone.utc)
                data["revoked_jtis"] = {
                    k: v for k, v in revoked.items() if datetime.fromisoformat(v) > now
                }
                _save_auth(data)
        except Exception as exc:
            logger.warning("Could not persist revoked JTI %s: %s", jti, exc)


def is_revoked(jti: str) -> bool:
    with _revoked_lock:
        return jti in _revoked_jtis


def cleanup_revoked_jtis() -> int:
    """Remove expired JTIs from disk and memory. Returns count removed."""
    now = datetime.now(timezone.utc)
    with _auth_lock:
        data = _load_auth()
        revoked = data.get("revoked_jtis", {})
        live = {k: v for k, v in revoked.items() if datetime.fromisoformat(v) > now}
        removed = len(revoked) - len(live)
        if removed:
            data["revoked_jtis"] = live
            _save_auth(data)
    if removed:
        # Sync memory: keep only JTIs still in the live set
        with _revoked_lock:
            _revoked_jtis.intersection_update(live.keys())
    return removed
