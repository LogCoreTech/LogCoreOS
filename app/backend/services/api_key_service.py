"""API keys — two kinds, both created and managed only by admins
(Admin → API Keys; docs/MEMORY.md 2026-10-25):

- **integration** — a machine credential that belongs to the INSTANCE, not to
  a person (e.g. a website's lead form). It is pinned at creation to a shared
  contacts list (`target`: "_team" or "_household") and can only do what its
  narrow write-only scope allows (`leads:create`). It survives any one
  admin's account being deleted or demoted — the machine side of
  docs/MEMORY.md 2026-07-12's "humans → accounts, machines → machine
  credentials" split, scoped down from the all-powerful automation token.
- **mcp** — a credential for the admin who created it (an AI app acting as
  that person over MCP). Carries per-group tool access (`access`,
  `tool_overrides`; see services/mcp_service.py). Dies with its owner's
  account or admin role.

Used only by routes that opt in through
`routers.auth.deps.require_api_key(scope)`; `get_current_user` rejects a key
outright, so a key can never reach a normal app/admin route.

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

KIND_INTEGRATION = "integration"
KIND_MCP = "mcp"
KINDS = (KIND_INTEGRATION, KIND_MCP)

# kind -> the one scope that kind carries. A scope names the routes a key may
# call (require_api_key); what an MCP key may do inside /mcp is its `access`.
SCOPE_FOR_KIND = {KIND_INTEGRATION: "leads:create", KIND_MCP: "mcp"}

# Integration keys write into a shared pool — each pool lives at the workspace
# the app reads it from (contacts_service.pool_for).
INTEGRATION_TARGETS = {"_team": "business", "_household": "personal"}

EXPIRY_DAYS = (30, 90, 365)
MAX_ACTIVE_KEYS = 50
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
    """Instance-wide switch (Admin → API Keys). Defaults on; off rejects every
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


def list_keys() -> list[dict]:
    """Every key, metadata only (never the hash), newest first."""
    return [_public(k) for k in sorted(_all(), key=lambda k: k["created_at"], reverse=True)]


def _clean_name(name: str) -> str:
    name = (name or "").strip()[:_NAME_MAX]
    if not name:
        raise ValueError("Give the key a name so you can recognize it later")
    return name


def create_key(
    creator: dict,
    kind: str,
    name: str,
    expires_days: int | None,
    *,
    target: str | None = None,
    workspace: str | None = None,
    access: dict | None = None,
    tool_overrides: dict | None = None,
) -> tuple[dict, str]:
    """Returns (metadata, full_key). The full key is never retrievable again.

    integration: `target` ("_team"/"_household") is required.
    mcp: `workspace` and a non-empty `access`/`tool_overrides` grant are
    required; the key belongs to `creator`."""
    if kind not in KINDS:
        raise ValueError("kind must be 'integration' or 'mcp'")
    name = _clean_name(name)
    if expires_days is not None and expires_days not in EXPIRY_DAYS:
        raise ValueError("expires_days must be 30, 90, 365, or empty for no expiry")

    now = _now()
    record: dict = {
        "id": secrets.token_hex(4),
        "kind": kind,
        "name": name,
        "scopes": [SCOPE_FOR_KIND[kind]],
        "created_by_id": creator["id"],
        "created_by_name": creator.get("name", ""),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=expires_days)).isoformat() if expires_days else None,
        "last_used_at": None,
        "revoked_at": None,
    }
    if kind == KIND_INTEGRATION:
        if target not in INTEGRATION_TARGETS:
            raise ValueError("Pick where leads go: the Team or Household contacts")
        record.update(
            {
                "target": target,
                "workspace": INTEGRATION_TARGETS[target],
                # Follow-up dates are "today + N" in the creating admin's timezone,
                # snapshotted so the key keeps working if that account goes away.
                "timezone": creator.get("timezone") or "UTC",
                "user_id": None,
            }
        )
    else:
        workspace = workspace or "personal"
        if workspace not in (creator.get("workspaces") or ["personal"]):
            raise ValueError(f"You don't have access to the {workspace!r} workspace")
        from services.mcp_service import validate_access

        clean_access, clean_overrides = validate_access(access or {}, tool_overrides or {})
        record.update(
            {
                "workspace": workspace,
                "user_id": creator["id"],
                "user_name": creator.get("name", ""),
                "access": clean_access,
                "tool_overrides": clean_overrides,
            }
        )

    secret = secrets.token_urlsafe(32)
    record["secret_hash"] = _hash(secret)

    def _add(current):
        keys = (current or {}).get("keys", [])
        if sum(1 for k in keys if _status(k) == "active") >= MAX_ACTIVE_KEYS:
            raise ValueError(f"There are already {MAX_ACTIVE_KEYS} active keys — revoke one first")
        if any(k["id"] == record["id"] for k in keys):  # 1 in 4 billion; just refuse
            raise ValueError("Key id collision — please try again")
        keys.append(record)
        return {"keys": keys}

    update_json(_path(), _add, default={"keys": []})
    return _public(record), f"{KEY_PREFIX}{record['id']}_{secret}"


def update_key(
    key_id: str,
    *,
    name: str | None = None,
    access: dict | None = None,
    tool_overrides: dict | None = None,
) -> dict | None:
    """Rename any active key, or change an active MCP key's tool access. The
    secret never changes. Returns the updated metadata, or None if not found."""
    changes: dict = {}
    if name is not None:
        changes["name"] = _clean_name(name)
    if access is not None or tool_overrides is not None:
        from services.mcp_service import validate_access

        existing = next((k for k in _all() if k["id"] == key_id), None)
        if existing is None:
            return None
        if existing.get("kind") != KIND_MCP:
            raise ValueError("Only MCP keys have tool access to change")
        clean_access, clean_overrides = validate_access(
            existing.get("access", {}) if access is None else access,
            existing.get("tool_overrides", {}) if tool_overrides is None else tool_overrides,
        )
        changes.update({"access": clean_access, "tool_overrides": clean_overrides})
    result: dict = {}

    def _apply(current):
        keys = (current or {}).get("keys", [])
        for k in keys:
            if k["id"] == key_id:
                if _status(k) != "active":
                    raise ValueError("Only an active key can be changed")
                k.update(changes)
                result["key"] = k
        return {"keys": keys}

    update_json(_path(), _apply, default={"keys": []})
    return _public(result["key"]) if result else None


def revoke_key(key_id: str) -> dict | None:
    """Revoke one key. Idempotent; None if no such key."""
    result: dict = {}

    def _revoke(current):
        keys = (current or {}).get("keys", [])
        for k in keys:
            if k["id"] == key_id:
                if not k.get("revoked_at"):
                    k["revoked_at"] = _now().isoformat()
                result["key"] = k
        return {"keys": keys}

    update_json(_path(), _revoke, default={"keys": []})
    return _public(result["key"]) if result else None


def revoke_all_for_user(user_id: str) -> int:
    """Called when an account is deleted: revokes the MCP keys it OWNS.
    Integration keys it merely created belong to the instance and stay."""
    count = {"n": 0}

    def _revoke(current):
        keys = (current or {}).get("keys", [])
        for k in keys:
            if k.get("user_id") == user_id and not k.get("revoked_at"):
                k["revoked_at"] = _now().isoformat()
                count["n"] += 1
        return {"keys": keys}

    update_json(_path(), _revoke, default={"keys": []})
    return count["n"]


def authenticate(raw: str) -> dict | None:
    """The active key record (metadata) for a presented key, or None.
    Constant-time hash compare; revoked/expired keys and a disabled instance
    switch all fail."""
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
