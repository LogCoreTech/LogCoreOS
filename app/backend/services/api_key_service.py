"""API keys — Admin → Integrations & MCP (docs/MEMORY.md 2026-10-25). Two kinds,
both set up only by admins:

- **integration** — a machine credential that belongs to the INSTANCE, not to
  a person (e.g. a website's lead form). Pinned at creation to a shared
  contacts list (`target`: "_team" or "_household") and limited to its one
  write-only scope (`leads:create`). The creating admin gets the key once,
  directly. Survives any one admin's account being deleted or demoted.
- **mcp** — a credential for ONE user (any role), chosen by the admin, so an AI
  app can act as that person over MCP with the tools the admin picked, set
  per workspace (`grants: {workspace: {access, tool_overrides}}`; see
  services/mcp_service.py). It's an
  invitation: the key is created only when that user accepts it (with their
  password), shown once to them alone — the admin never sees it, so an admin
  can't quietly act as someone else. Pending invites expire after 7 days.
  Widening an accepted key's tools needs the user's approval again;
  narrowing applies at once. Users can't create or change MCP keys, only
  request one, accept/decline, and revoke their own.

Used only by routes that opt in through
`routers.auth.deps.require_api_key(scope)`; `get_current_user` rejects a key
outright, so a key can never reach a normal app/admin route.

Stored in brain/_system/api_keys.json (`keys` + `requests`). Only a SHA-256
hash of each key's secret is kept (the secret is 256 bits of randomness, so a
slow KDF adds nothing). Key format: ``lcos_<8 hex id>_<urlsafe secret>``.
"""

import hashlib
import secrets
import time
import uuid
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
INVITE_DAYS = 7
MAX_ACTIVE_KEYS = 50
_NAME_MAX = 60
_NOTE_MAX = 500
_LAST_USED_EVERY = 60  # seconds — don't rewrite the file on every request

_last_used_written: dict[str, float] = {}


def _path() -> Path:
    return brain_path() / "_system" / "api_keys.json"


def _default() -> dict:
    return {"keys": [], "requests": []}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _mutate(fn):
    """update_json() over the whole file, keeping both lists intact."""

    def _apply(current):
        data = {**_default(), **(current or {})}
        fn(data)
        return data

    return update_json(_path(), _apply, default=_default())


def keys_enabled() -> bool:
    """Instance-wide switch. Defaults on; off rejects every key immediately
    without deleting any, and blocks creating/accepting new ones."""
    from services.auth_service import get_system_settings

    return bool(get_system_settings().get("api_keys_enabled", True))


def _status(record: dict) -> str:
    if record.get("revoked_at"):
        return "revoked"
    if record.get("declined_at"):
        return "declined"
    if not record.get("secret_hash"):  # an MCP invite nobody has accepted yet
        invite_expires = record.get("invite_expires_at")
        if invite_expires and datetime.fromisoformat(invite_expires) <= _now():
            return "expired"
        return "pending"
    expires = record.get("expires_at")
    if expires and datetime.fromisoformat(expires) <= _now():
        return "expired"
    return "active"


def _public(record: dict) -> dict:
    out = {k: v for k, v in record.items() if k != "secret_hash"}
    out["status"] = _status(record)
    return out


def _all() -> list[dict]:
    return read_json(_path(), default=_default()).get("keys", [])


def get_key(key_id: str) -> dict | None:
    record = next((k for k in _all() if k["id"] == key_id), None)
    return _public(record) if record else None


def list_keys() -> list[dict]:
    """Every key, metadata only (never the hash), newest first."""
    return [_public(k) for k in sorted(_all(), key=lambda k: k["created_at"], reverse=True)]


def list_user_keys(user_id: str) -> list[dict]:
    """The MCP keys that act as this user, newest first."""
    return [k for k in list_keys() if k.get("user_id") == user_id]


def _clean_name(name: str) -> str:
    name = (name or "").strip()[:_NAME_MAX]
    if not name:
        raise ValueError("Give the key a name so you can recognize it later")
    return name


def _check_expiry(expires_days: int | None) -> None:
    if expires_days is not None and expires_days not in EXPIRY_DAYS:
        raise ValueError("expires_days must be 30, 90, 365, or empty for no expiry")


def usable_workspaces(user: dict) -> list[str]:
    from services.auth_service import enabled_workspaces

    enabled = enabled_workspaces()
    if user.get("role") == "admin":  # get_current_user grants admins every one
        return enabled
    return [w for w in (user.get("workspaces") or ["personal"]) if w in enabled]


def _base_record(creator: dict, kind: str, name: str) -> dict:
    return {
        "id": secrets.token_hex(4),
        "kind": kind,
        "name": _clean_name(name),
        "scopes": [SCOPE_FOR_KIND[kind]],
        "created_by_id": creator["id"],
        "created_by_name": creator.get("name", ""),
        "created_at": _now().isoformat(),
        "expires_at": None,
        "last_used_at": None,
        "revoked_at": None,
    }


def _append_key(record: dict) -> None:
    def _add(data):
        keys = data["keys"]
        if sum(1 for k in keys if _status(k) in ("active", "pending")) >= MAX_ACTIVE_KEYS:
            raise ValueError(f"There are already {MAX_ACTIVE_KEYS} keys in use — revoke one first")
        if any(k["id"] == record["id"] for k in keys):  # 1 in 4 billion; just refuse
            raise ValueError("Key id collision — please try again")
        keys.append(record)

    _mutate(_add)


def create_integration_key(
    creator: dict, name: str, target: str, expires_days: int | None
) -> tuple[dict, str]:
    """Returns (metadata, full_key) — the full key is never retrievable again."""
    _check_expiry(expires_days)
    if target not in INTEGRATION_TARGETS:
        raise ValueError("Pick where leads go: the Team or Household contacts")
    record = _base_record(creator, KIND_INTEGRATION, name)
    secret = secrets.token_urlsafe(32)
    record.update(
        {
            "target": target,
            "workspace": INTEGRATION_TARGETS[target],
            # Follow-up dates are "today + N" in the creating admin's timezone,
            # snapshotted so the key keeps working if that account goes away.
            "timezone": creator.get("timezone") or "UTC",
            "user_id": None,
            "secret_hash": _hash(secret),
        }
    )
    if expires_days:
        record["expires_at"] = (_now() + timedelta(days=expires_days)).isoformat()
    _append_key(record)
    return _public(record), f"{KEY_PREFIX}{record['id']}_{secret}"


def grants_of(record: dict) -> dict:
    """An MCP key's per-workspace grants: {workspace: {access, tool_overrides}}.
    Also reads the earlier single-workspace shape (`workspace` + `access` +
    `tool_overrides`) so a key stored before per-workspace grants still works."""
    if record.get("grants") is not None:
        return record["grants"]
    if record.get("access") is not None or record.get("tool_overrides") is not None:
        return {
            record.get("workspace")
            or "personal": {
                "access": record.get("access") or {},
                "tool_overrides": record.get("tool_overrides") or {},
            }
        }
    return {}


def _grant_pairs(grants: dict) -> set[tuple[str, str]]:
    from services.mcp_service import granted_tools

    return {(t["workspace"], t["name"]) for t in granted_tools(grants)}


def _user_workspaces(user_id: str) -> list[str]:
    from services.auth_service import get_user_by_id

    user = get_user_by_id(user_id)
    return usable_workspaces(user) if user else []


def invite_mcp_key(
    creator: dict,
    for_user: dict,
    name: str,
    grants: dict,
    expires_days: int | None,
) -> dict:
    """Create a PENDING MCP key for `for_user` with per-workspace `grants`. No
    secret exists until they accept — the creating admin never gets one.
    Marks that user's open access requests handled. Returns metadata."""
    from services.mcp_service import validate_grants

    _check_expiry(expires_days)
    clean = validate_grants(grants or {}, usable_workspaces(for_user))
    record = _base_record(creator, KIND_MCP, name)
    record.update(
        {
            "user_id": for_user["id"],
            "user_name": for_user.get("name", ""),
            "grants": clean,
            "expires_days": expires_days,
            "invite_expires_at": (_now() + timedelta(days=INVITE_DAYS)).isoformat(),
            "accepted_at": None,
            "declined_at": None,
            "proposed_grants": None,
            "secret_hash": None,
        }
    )
    _append_key(record)

    def _handle_requests(data):
        for r in data["requests"]:
            if r["user_id"] == for_user["id"] and r["status"] == "open":
                r["status"] = "handled"
                r["handled_at"] = _now().isoformat()

    _mutate(_handle_requests)
    return _public(record)


def _own_pending_or_active(data: dict, key_id: str, user_id: str, want: tuple[str, ...]) -> dict:
    record = next((k for k in data["keys"] if k["id"] == key_id), None)
    if record is None or record.get("user_id") != user_id or record["kind"] != KIND_MCP:
        raise LookupError("Key not found")
    if _status(record) not in want:
        raise ValueError(f"This key is {_status(record)}")
    return record


def accept_invite(key_id: str, user: dict) -> tuple[dict, str]:
    """The invited user accepts: the secret is generated NOW and returned once.
    Raises LookupError if it isn't their invite, ValueError if not pending."""
    secret = secrets.token_urlsafe(32)
    result: dict = {}

    def _accept(data):
        record = _own_pending_or_active(data, key_id, user["id"], ("pending",))
        now = _now()
        record["secret_hash"] = _hash(secret)
        record["accepted_at"] = now.isoformat()
        days = record.get("expires_days")
        record["expires_at"] = (now + timedelta(days=days)).isoformat() if days else None
        result["key"] = record

    _mutate(_accept)
    return _public(result["key"]), f"{KEY_PREFIX}{key_id}_{secret}"


def decline_invite(key_id: str, user: dict) -> dict:
    result: dict = {}

    def _decline(data):
        record = _own_pending_or_active(data, key_id, user["id"], ("pending",))
        record["declined_at"] = _now().isoformat()
        result["key"] = record

    _mutate(_decline)
    return _public(result["key"])


def update_key(
    key_id: str,
    *,
    name: str | None = None,
    grants: dict | None = None,
) -> tuple[dict, bool] | None:
    """Rename any active/pending key, or change an MCP key's per-workspace
    tools. Returns (metadata, needs_approval) or None if not found. Narrowing
    (or editing a still-pending invite) applies at once; WIDENING an accepted
    key — any new (workspace, tool) pair — is stored as a proposal the user
    must approve; until then the old grants stand."""
    existing = next((k for k in _all() if k["id"] == key_id), None)
    if existing is None:
        return None
    changes: dict = {}
    needs_approval = False
    if name is not None:
        changes["name"] = _clean_name(name)
    if grants is not None:
        if existing["kind"] != KIND_MCP:
            raise ValueError("Only MCP keys have tools to change")
        from services.mcp_service import validate_grants

        new = validate_grants(grants, _user_workspaces(existing["user_id"]))
        widened = _grant_pairs(new) - _grant_pairs(grants_of(existing))
        if _status(existing) == "active" and widened:
            changes["proposed_grants"] = new
            needs_approval = True
        else:
            changes.update({"grants": new, "proposed_grants": None})
    result: dict = {}

    def _apply(data):
        for k in data["keys"]:
            if k["id"] == key_id:
                if _status(k) not in ("active", "pending"):
                    raise ValueError("Only an active or pending key can be changed")
                k.update(changes)
                for legacy in ("workspace", "access", "tool_overrides"):
                    if "grants" in changes:
                        k.pop(legacy, None)
                result["key"] = k

    _mutate(_apply)
    return _public(result["key"]), needs_approval


def respond_to_change(key_id: str, user: dict, accept: bool) -> dict:
    """The key's user approves or rejects a proposed widening of its tools."""
    result: dict = {}

    def _respond(data):
        record = _own_pending_or_active(data, key_id, user["id"], ("active",))
        if record.get("proposed_grants") is None:
            raise ValueError("There's no change waiting for approval")
        if accept:
            record["grants"] = record["proposed_grants"]
            for legacy in ("workspace", "access", "tool_overrides"):
                record.pop(legacy, None)
        record["proposed_grants"] = None
        result["key"] = record

    _mutate(_respond)
    return _public(result["key"])


def revoke_key(key_id: str, user_id: str | None = None) -> dict | None:
    """Revoke one key (pending invites too). With `user_id`, only a key acting
    as that user matches — a user revoking their own. Idempotent."""
    result: dict = {}

    def _revoke(data):
        for k in data["keys"]:
            if k["id"] == key_id and (user_id is None or k.get("user_id") == user_id):
                if not k.get("revoked_at"):
                    k["revoked_at"] = _now().isoformat()
                result["key"] = k

    _mutate(_revoke)
    return _public(result["key"]) if result else None


def revoke_all_for_user(user_id: str) -> int:
    """Called when an account is deleted: revokes every MCP key acting as it
    and closes its requests. Integration keys it merely created stay."""
    count = {"n": 0}

    def _revoke(data):
        for k in data["keys"]:
            if k.get("user_id") == user_id and not k.get("revoked_at"):
                k["revoked_at"] = _now().isoformat()
                count["n"] += 1
        for r in data["requests"]:
            if r["user_id"] == user_id and r["status"] == "open":
                r["status"] = "dismissed"

    _mutate(_revoke)
    return count["n"]


# --- access requests ------------------------------------------------------------


def create_request(user: dict, note: str) -> dict:
    """A user asks admins for MCP access. One open request per user."""
    note = (note or "").strip()[:_NOTE_MAX]
    result: dict = {}

    def _add(data):
        if any(r["user_id"] == user["id"] and r["status"] == "open" for r in data["requests"]):
            raise ValueError("You already have a request waiting for an admin")
        request = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "user_name": user.get("name", ""),
            "note": note,
            "created_at": _now().isoformat(),
            "status": "open",
        }
        data["requests"].append(request)
        data["requests"] = data["requests"][-200:]
        result["request"] = request

    _mutate(_add)
    return result["request"]


def list_requests(status: str = "open") -> list[dict]:
    requests = read_json(_path(), default=_default()).get("requests", [])
    return [r for r in reversed(requests) if r["status"] == status]


def has_open_request(user_id: str) -> bool:
    return any(r["user_id"] == user_id for r in list_requests())


def dismiss_request(request_id: str) -> dict | None:
    result: dict = {}

    def _dismiss(data):
        for r in data["requests"]:
            if r["id"] == request_id and r["status"] == "open":
                r["status"] = "dismissed"
                result["request"] = r

    _mutate(_dismiss)
    return result.get("request")


# --- authentication ------------------------------------------------------------------


def authenticate(raw: str) -> dict | None:
    """The active key record (metadata) for a presented key, or None.
    Constant-time hash compare; pending/declined/revoked/expired keys and a
    disabled instance switch all fail."""
    if not raw or not raw.startswith(KEY_PREFIX) or not keys_enabled():
        return None
    parts = raw[len(KEY_PREFIX) :].split("_", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    key_id, secret = parts
    record = next((k for k in _all() if k["id"] == key_id), None)
    if record is None or not record.get("secret_hash"):
        return None
    if not secrets.compare_digest(record["secret_hash"], _hash(secret)):
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

    def _set(data):
        for k in data["keys"]:
            if k["id"] == key_id:
                k["last_used_at"] = stamp

    _mutate(_set)
