"""Personal API keys (services/api_key_service.py, routers/auth/api_keys.py,
routers/auth/deps.py:require_api_key). Admin-only by owner decision
(docs/MEMORY.md 2026-10-25). Covers: hash-only storage, shown-once key,
revoke/expiry/instance switch, scope enforcement, the session path refusing a
key outright, owner demotion/deletion, workspace re-validation, disabled
modules riding along, and the per-key rate limit."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from routers.auth import (
    AdminSettingsRequest,
    ApiKeyCreateRequest,
    admin_create_api_key,
    admin_list_api_keys,
    admin_revoke_api_key,
    update_admin_settings,
)
from routers.auth.deps import get_current_user, require_api_key
from services import api_key_service, audit_log, auth_service
from services import rate_limiter as rl
from services.file_service import read_json


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    rl._hits.clear()
    api_key_service._last_used_written.clear()
    yield
    rl._hits.clear()


@pytest.fixture()
def admin(brain):
    user = auth_service.create_user("admin@example.com", "password123", "Admin", role="admin")
    # What get_current_user() grants a real admin request (every enabled workspace).
    auth_service.update_user(user["id"], {"workspaces": ["personal", "business"]})
    return auth_service.get_user_by_id(user["id"])


def _create(admin, scopes=("mcp:read",), **kw):
    req = ApiKeyCreateRequest(
        name=kw.pop("name", "laptop"),
        scopes=list(scopes),
        current_password=kw.pop("current_password", "password123"),
        **kw,
    )
    return admin_create_api_key(req, admin, None)


def _creds(key: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=key)


def _use(key: str, scope: str = "mcp:read") -> dict:
    return require_api_key(scope)(_creds(key))


# --- creation & storage -----------------------------------------------------


def test_create_returns_key_once_and_stores_only_a_hash(admin):
    result = _create(admin)
    key = result["key"]
    assert key.startswith("lcos_")
    raw = read_json(api_key_service._path())
    stored = raw["keys"][0]
    assert key.split("_", 2)[2] not in str(raw)
    assert stored["secret_hash"] != key
    assert "secret_hash" not in result["meta"]
    listed = admin_list_api_keys(admin, None)
    assert "secret_hash" not in str(listed)
    assert listed["keys"][0]["status"] == "active"


def test_create_requires_correct_password(admin):
    with pytest.raises(HTTPException) as exc:
        _create(admin, current_password="wrong-password")
    assert exc.value.status_code == 400
    assert api_key_service.list_keys() == []


def test_create_rejects_unknown_scope_and_bad_expiry(admin):
    with pytest.raises(HTTPException):
        _create(admin, scopes=("everything",))
    with pytest.raises(HTTPException):
        _create(admin, expires_days=7)


def test_create_and_revoke_are_audited(admin):
    meta = _create(admin)["meta"]
    admin_revoke_api_key(meta["id"], admin, None)
    actions = [e["action"] for e in audit_log.list_entries(10)]
    assert "api_key.create" in actions and "api_key.revoke" in actions


# --- using a key -------------------------------------------------------------


def test_valid_key_resolves_to_owner_with_key_context(admin):
    key = _create(admin)["key"]
    user = _use(key)
    assert user["id"] == admin["id"]
    assert user["_workspace"] == "personal"
    assert user["_api_key"]["scopes"] == ["mcp:read"]
    assert "disabled_modules" in user


def test_wrong_secret_and_garbage_are_rejected(admin):
    key = _create(admin)["key"]
    for bad in (key[:-2] + "xx", "lcos_", "lcos_abc", "not-a-key", ""):
        with pytest.raises(HTTPException) as exc:
            _use(bad)
        assert exc.value.status_code == 401


def test_missing_scope_is_forbidden(admin):
    key = _create(admin, scopes=("leads:create",))["key"]
    with pytest.raises(HTTPException) as exc:
        _use(key, "mcp:read")
    assert exc.value.status_code == 403


def test_revoked_key_stops_working(admin):
    result = _create(admin)
    admin_revoke_api_key(result["meta"]["id"], admin, None)
    with pytest.raises(HTTPException) as exc:
        _use(result["key"])
    assert exc.value.status_code == 401


def test_expired_key_stops_working(admin):
    result = _create(admin, expires_days=30)

    def _expire(current):
        current["keys"][0]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        return current

    from services.file_service import update_json

    update_json(api_key_service._path(), _expire)
    with pytest.raises(HTTPException):
        _use(result["key"])
    assert api_key_service.list_keys()[0]["status"] == "expired"


def test_instance_switch_off_rejects_every_key(admin):
    key = _create(admin)["key"]
    update_admin_settings(AdminSettingsRequest(api_keys_enabled=False), admin, None)
    with pytest.raises(HTTPException):
        _use(key)
    with pytest.raises(HTTPException) as exc:
        _create(admin)
    assert exc.value.status_code == 409
    update_admin_settings(AdminSettingsRequest(api_keys_enabled=True), admin, None)
    assert _use(key)["id"] == admin["id"]


def test_session_path_refuses_api_keys(admin):
    key = _create(admin)["key"]
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    with pytest.raises(HTTPException) as exc:
        get_current_user(request, _creds(key), "personal")
    assert exc.value.status_code == 401
    assert "API keys" in exc.value.detail


def test_demoted_owner_key_stops_working(admin):
    key = _create(admin)["key"]
    auth_service.create_user("other@example.com", "password123", "Other", role="admin")
    auth_service.update_user_role(admin["id"], "member")
    with pytest.raises(HTTPException) as exc:
        _use(key)
    assert exc.value.status_code == 401


def test_deleting_owner_revokes_their_keys(admin):
    key = _create(admin)["key"]
    auth_service.delete_user(admin["id"])
    assert api_key_service.list_keys()[0]["status"] == "revoked"
    with pytest.raises(HTTPException):
        _use(key)


def test_workspace_no_longer_available_is_forbidden(admin):
    key = _create(admin, workspace="business")["key"]
    assert _use(key)["_workspace"] == "business"
    auth_service.update_system_settings({"enabled_workspaces": ["personal"]})
    with pytest.raises(HTTPException) as exc:
        _use(key)
    assert exc.value.status_code == 403


def test_owner_disabled_modules_apply_to_the_key(admin):
    key = _create(admin)["key"]
    auth_service.update_user(admin["id"], {"disabled_modules": ["contacts"]})
    assert "contacts" in _use(key)["disabled_modules"]


def test_per_key_rate_limit(admin):
    key = _create(admin)["key"]
    dep = require_api_key("mcp:read", max_calls=3, window_seconds=60)
    for _ in range(3):
        dep(_creds(key))
    with pytest.raises(HTTPException) as exc:
        dep(_creds(key))
    assert exc.value.status_code == 429


def test_last_used_is_recorded(admin):
    key = _create(admin)["key"]
    assert api_key_service.list_keys()[0]["last_used_at"] is None
    _use(key)
    assert api_key_service.list_keys()[0]["last_used_at"] is not None


def test_active_key_cap(admin, monkeypatch):
    monkeypatch.setattr(api_key_service, "MAX_ACTIVE_KEYS_PER_USER", 2)
    _create(admin)
    _create(admin)
    with pytest.raises(HTTPException):
        _create(admin)
