"""Personal API keys — a credential FOR an existing admin account, not a new
identity (docs/MEMORY.md 2026-10-25). Used only by the narrow machine
surfaces that opt in through `routers.auth.deps.require_api_key(scope)`:
the lead-intake endpoint and the MCP server. `get_current_user` rejects a
key outright, so a key can never reach a normal app/admin route.

Stored in brain/_system/api_keys.json. Only a SHA-256 hash of each key's
secret is kept (the secret is 256 bits of randomness, so a slow KDF adds
nothing); the full key is returned exactly once, at creation.

Key format: ``lcos_<8 hex id>_<urlsafe secret>`` — the id lets a lookup go
straight to one record, and the prefix makes a leaked key easy to grep for.
"""

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.file_service import brain_path, read_json, update_json

KEY_PREFIX = "lcos_"

# scope -> what it allows. Every scope is opt-in (a new key has none until
# chosen); read access to personal data is deliberately a separate scope from
# the write-only intake one (docs/MEMORY.md 2026-07-14).
SCOPES = {
    "leads:create": "Send new leads in (write-only, nothing can be read back)",
    "mcp:read": "MCP: read-only tools",
    "mcp:write": "MCP: tools that create or change data",
}
EXPIRY_DAYS = (30, 90, 365)
MAX_ACTIVE_KEYS_PER_USER = 20
_NAME_MAX = 60
_LAST_USED_EVERY = 60  # seconds — don't rewrite the file on every request

_last_used_written: dict[str, float] = {}


def _path() -> Path:
    return brain_path() / "_system" / "api_keys.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def keys_enabled() -> bool:
    """Instance-wide switch (Admin → General). Defaults on; off rejects every
    key immediately without deleting any."""
    from services.auth_service import get_system_settings

    return bool(get_system_settings().get("api_keys_enabled", True))


def _public(record: dict) -> dict:
    out = {k: v for k, v in record.items() if k != "secret_hash"}
    out["status"] = _status(record)
    return out


def _status(record: dict) -> str:
    if record.get("revoked_at"):
        return "revoked"
    expires = record.get("expires_at")
    if expires and datetime.fromisoformat(expires) <= _now():
        return "expired"
    return "active"


def _all() -> list[dict]:
    return read_json(_path(), default={"keys": []}).get("keys", [])


def list_keys(user_id: str | None = None) -> list[dict]:
    """Metadata only (never the hash), newest first. `user_id=None` = every key."""
    keys = [k for k in _all() if user_id is None or k["user_id"] == user_id]
    return [_public(k) for k in sorted(keys, key=lambda k: k["created_at"], reverse=True)]


def create_key(
    user: dict,
    name: str,
    scopes: list[str],
    workspace: str,
    expires_days: int | None,
) -> tuple[dict, str]:
    """Returns (metadata, full_key). The full key is never retrievable again."""
    name = (name or "").strip()[:_NAME_MAX]
    if not name:
        raise ValueError("Give the key a name so you can recognize it later")
    clean_scopes = sorted(set(scopes or []))
    if not clean_scopes:
        raise ValueError("Pick at least one scope")
    unknown = [s for s in clean_scopes if s not in SCOPES]
    if unknown:
        raise ValueError(f"Unknown scope(s): {', '.join(unknown)}")
    if workspace not in (user.get("workspaces") or ["personal"]):
        raise ValueError(f"You don't have access to the {workspace!r} workspace")
    if expires_days is not None and expires_days not in EXPIRY_DAYS:
        raise ValueError("expires_days must be 30, 90, 365, or empty for no expiry")

    key_id = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    now = _now()
    record = {
        "id": key_id,
        "user_id": user["id"],
        "user_name": user.get("name", ""),
        "name": name,
        "scopes": clean_scopes,
        "workspace": workspace,
        "secret_hash": _hash(secret),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=expires_days)).isoformat() if expires_days else None,
        "last_used_at": None,
        "revoked_at": None,
    }

    def _add(current):
        keys = (current or {}).get("keys", [])
        active = [k for k in keys if k["user_id"] == user["id"] and _status(k) == "active"]
        if len(active) >= MAX_ACTIVE_KEYS_PER_USER:
            raise ValueError(
                f"You already have {MAX_ACTIVE_KEYS_PER_USER} active keys — revoke one first"
            )
        if any(k["id"] == key_id for k in keys):  # 1 in 4 billion; just refuse
            raise ValueError("Key id collision — please try again")
        keys.append(record)
        return {"keys": keys}

    update_json(_path(), _add, default={"keys": []})
    return _public(record), f"{KEY_PREFIX}{key_id}_{secret}"


def revoke_key(key_id: str, user_id: str | None = None) -> dict | None:
    """Revoke one key. With `user_id`, only that user's own key matches (so a
    user can't revoke someone else's by guessing an id). Idempotent."""
    result: dict = {}

    def _revoke(current):
        keys = (current or {}).get("keys", [])
        for k in keys:
            if k["id"] == key_id and (user_id is None or k["user_id"] == user_id):
                if not k.get("revoked_at"):
                    k["revoked_at"] = _now().isoformat()
                result["key"] = k
        return {"keys": keys}

    update_json(_path(), _revoke, default={"keys": []})
    return _public(result["key"]) if result else None


def revoke_all_for_user(user_id: str) -> int:
    """Called when an account is deleted. Returns how many keys were revoked."""
    count = {"n": 0}

    def _revoke(current):
        keys = (current or {}).get("keys", [])
        for k in keys:
            if k["user_id"] == user_id and not k.get("revoked_at"):
                k["revoked_at"] = _now().isoformat()
                count["n"] += 1
        return {"keys": keys}

    update_json(_path(), _revoke, default={"keys": []})
    return count["n"]


def authenticate(raw: str) -> dict | None:
    """The active key record for a presented key, or None. Constant-time hash
    compare; revoked/expired keys and a disabled instance switch all fail."""
    if not raw or not raw.startswith(KEY_PREFIX) or not keys_enabled():
        return None
    parts = raw[len(KEY_PREFIX) :].split("_", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    key_id, secret = parts
    record = next((k for k in _all() if k["id"] == key_id), None)
    if record is None or not secrets.compare_digest(record["secret_hash"], _hash(secret)):
        return None
    if _status(record) != "active":
        return None
    _touch(key_id)
    return _public(record)


def _touch(key_id: str) -> None:
    now = time.monotonic()
    if now - _last_used_written.get(key_id, -_LAST_USED_EVERY) < _LAST_USED_EVERY:
        return
    _last_used_written[key_id] = now
    stamp = _now().isoformat()

    def _set(current):
        keys = (current or {}).get("keys", [])
        for k in keys:
            if k["id"] == key_id:
                k["last_used_at"] = stamp
        return {"keys": keys}

    update_json(_path(), _set, default={"keys": []})
