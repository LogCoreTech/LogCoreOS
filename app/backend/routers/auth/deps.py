"""Core auth dependencies — the functions nearly every other router in the
app imports (`get_current_user`, `get_workspace`, `require_admin`,
`require_module`, `require_pool_edit`), plus the small shared bits their
siblings (session.py/profile.py/admin_users.py/admin_settings.py) need too:
the auth cookie name/helpers, the bearer-token scheme, and a couple of
genuinely cross-cutting constants/helpers (`_admin_limit`, `_validate_timezone`,
`_VALID_WORKSPACES`) that are each used by more than one sibling file. Split
out of a single ~1230-line routers/auth.py — see routers/auth/__init__.py's
own docstring for the full rationale and module_packages/finance/manifest.py's
`_get_router()` for the precedent this split follows."""

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services import api_key_service, auth_service
from services.features_service import get_effective_disabled
from services.hosting_service import effective_cookie_secure
from services.rate_limiter import check_rate, rate_limit

bearer_optional = HTTPBearer(auto_error=False)
logger = logging.getLogger("logcore.auth")

_COOKIE = "lc_token"

# Shared across admin_users.py and admin_settings.py (both have admin-only
# mutation endpoints rate-limited the same way) — kept here rather than in
# either sibling so neither has to import from the other.
_admin_limit = rate_limit(20, 60)  # 20 admin ops per minute

# Shared by admin_users.py's WorkspacesRequest/WorkspaceModulesRequest and
# admin_settings.py's AdminSettingsRequest — same reasoning as _admin_limit.
_VALID_WORKSPACES = {"personal", "business"}


def _set_auth_cookie(response: Response, token: str, session_minutes: int) -> None:
    response.set_cookie(
        key=_COOKIE,
        value=token,
        httponly=True,
        secure=effective_cookie_secure(),
        samesite="lax",
        max_age=session_minutes * 60,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=_COOKIE, path="/", samesite="lax")


def _validate_timezone(tz: str) -> str:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, Exception):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timezone: '{tz}'. Use an IANA zone name like 'America/Chicago'.",
        )
    return tz


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_optional),
    x_workspace: str = Header(default="personal"),
) -> dict:
    # Accept httpOnly cookie first, then fall back to Authorization header
    token = request.cookies.get(_COOKIE)
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if token.startswith(api_key_service.KEY_PREFIX):
        # Fail closed: an API key only works on routes that explicitly opt in
        # via require_api_key(scope) — never on the app's normal routes.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API keys can't be used on this endpoint",
        )
    payload = auth_service.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    user = auth_service.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    # Attach jti and exp so logout can revoke with persistence
    user["_jti"] = payload.get("jti")
    user["_exp"] = payload.get("exp")
    return _apply_workspace_context(user, x_workspace)


def _apply_workspace_context(user: dict, requested_workspace: str) -> dict:
    """Effective workspaces, the validated active workspace, and disabled
    modules — shared by the session path (get_current_user) and the API-key
    path (require_api_key) so the two can never drift apart."""
    workspace = (
        requested_workspace if requested_workspace in ("personal", "business") else "personal"
    )
    enabled_ws = auth_service.enabled_workspaces()
    # Lazy migration: admins get every instance-enabled workspace (persisted so
    # access is restored automatically if a hidden workspace is re-enabled).
    if user.get("role") == "admin":
        want = [w for w in ("personal", "business") if w in enabled_ws]
        have = user.get("workspaces", [])
        if not set(want).issubset(set(have)):
            merged = sorted(set(have) | set(want))
            auth_service.update_user(user["id"], {"workspaces": merged})
            user["workspaces"] = merged
    # Hide instance-disabled workspaces from what the frontend sees (never empty).
    effective_ws = [w for w in user.get("workspaces", ["personal"]) if w in enabled_ws]
    if not effective_ws:
        effective_ws = [enabled_ws[0]]
    user["workspaces"] = effective_ws
    # Coerce a disabled/invalid OR not-entitled active workspace to an enabled
    # one before use — the X-Workspace header is caller-supplied and must
    # never be trusted past what this user's own `workspaces` actually grants.
    if workspace not in effective_ws:
        workspace = effective_ws[0]
    # Compute effective disabled modules for the current workspace
    user["disabled_modules"] = get_effective_disabled(
        user.get("feature_role", "member"),
        user.get("disabled_modules", []),
        workspace,
    )
    user["_workspace"] = workspace
    return user


def get_workspace(current_user: dict = Depends(get_current_user)) -> str:
    """The current request's workspace, already validated in get_current_user()
    against this user's own `workspaces` entitlement — every router depends on
    this (never the raw header) so that entitlement check applies everywhere."""
    return current_user["_workspace"]


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def require_module(module_id: str):
    """Dependency factory — blocks the endpoint if the module is disabled for this user."""

    def check(current_user: dict = Depends(get_current_user)) -> dict:
        if module_id in current_user.get("disabled_modules", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module_id}' has been disabled for your account.",
            )
        return current_user

    return check


def require_pool_edit(pool: str):
    """Dependency factory for pool (household/team) write access.

    Admins always pass. Otherwise the user must have been granted management
    rights for this pool — i.e. `pool` is in their per-user `pool_edit` list.
    Grants full pool-manager parity (add/edit/delete events + tasks + assign).
    A grant is default-off, so this cannot use the disabled_modules union model
    (which only ever adds restrictions); it is a dedicated per-user grant.
    """

    def check(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") == "admin":
            return current_user
        if pool in (current_user.get("pool_edit") or []):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to make changes here.",
        )

    return check


def require_api_key(scope: str | tuple[str, ...], max_calls: int = 30, window_seconds: int = 60):
    """Dependency factory for the few routes that accept a personal API key
    (services/api_key_service.py) instead of a session. Bearer header ONLY —
    the session cookie is ignored here, so a logged-in browser can never be
    used to drive these routes cross-site. Re-fetches the owning user on every
    request and re-applies their current role, modules, and workspace
    entitlements; the per-KEY rate limit sits on top of the route's per-IP one.
    A tuple `scope` accepts a key holding ANY of them (MCP: read or write).
    """
    accepted = (scope,) if isinstance(scope, str) else tuple(scope)
    bucket = "|".join(accepted)

    def check(credentials: HTTPAuthorizationCredentials = Depends(bearer_optional)) -> dict:
        record = api_key_service.authenticate(credentials.credentials if credentials else "")
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid, expired, or revoked API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        check_rate(f"apikey:{record['id']}:{bucket}", max_calls, window_seconds)
        if not set(accepted) & set(record["scopes"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This API key doesn't have the '{' or '.join(accepted)}' scope",
            )
        user = auth_service.get_user_by_id(record["user_id"])
        # Keys are admin-only (docs/MEMORY.md 2026-10-25): a key whose owner has
        # since been demoted stops working, it isn't grandfathered in.
        if not user or user.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This API key's account no longer exists or is no longer an admin",
            )
        user = _apply_workspace_context(user, record["workspace"])
        if user["_workspace"] != record["workspace"]:
            # Never silently retarget a key at a different workspace's data.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This API key's workspace ({record['workspace']}) is no longer available",
            )
        user["_api_key"] = {"id": record["id"], "name": record["name"], "scopes": record["scopes"]}
        return user

    return check
