"""API keys (services/api_key_service.py, routers/auth/api_keys.py,
routers/auth/deps.py:require_api_key). Admin-managed; two kinds
(docs/MEMORY.md 2026-10-25): **integration** keys belong to the instance and
are pinned to a shared contacts list; **mcp** keys belong to the admin who
created them and carry per-module tool access. Covers: hash-only storage,
shown-once key, revoke/expiry/instance switch, scope enforcement, the session
path refusing a key outright, owner demotion/deletion (MCP keys die, integration
keys survive), workspace re-validation, editing access, and the per-key rate
limit."""

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
    ApiKeyUpdateRequest,
    admin_create_api_key,
    admin_list_api_keys,
    admin_revoke_api_key,
    admin_update_api_key,
    update_admin_settings,
)
from routers.auth.deps import get_current_user, require_api_key
from services import api_key_service, audit_log, auth_service
from services import rate_limiter as rl
from services.file_service import read_json, update_json


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


def _create_mcp(admin, access=None, **kw):
    req = ApiKeyCreateRequest(
        kind="mcp",
        name=kw.pop("name", "Claude"),
        access={"tasks": "read"} if access is None else access,
        current_password=kw.pop("current_password", "password123"),
        **kw,
    )
    return admin_create_api_key(req, admin, None)


def _create_integration(admin, target="_team", **kw):
    req = ApiKeyCreateRequest(
        kind="integration",
        name=kw.pop("name", "Lead form"),
        target=target,
        current_password=kw.pop("current_password", "password123"),
        **kw,
    )
    return admin_create_api_key(req, admin, None)


def _creds(key: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=key)


def _use(key: str, scope: str = "mcp") -> dict:
    return require_api_key(scope)(_creds(key))


# --- creation & storage -----------------------------------------------------


def test_create_returns_key_once_and_stores_only_a_hash(admin):
    result = _create_mcp(admin)
    key = result["key"]
    assert key.startswith("lcos_")
    raw = read_json(api_key_service._path())
    assert key.split("_", 2)[2] not in str(raw)
    assert "secret_hash" not in result["meta"]
    listed = admin_list_api_keys(admin, None)
    assert "secret_hash" not in str(listed)
    assert listed["keys"][0]["status"] == "active"
    assert any(g["id"] == "tasks" for g in listed["mcp_catalog"])


def test_create_requires_correct_password(admin):
    with pytest.raises(HTTPException) as exc:
        _create_mcp(admin, current_password="wrong-password")
    assert exc.value.status_code == 400
    assert api_key_service.list_keys() == []


def test_create_validates_kind_specific_fields(admin):
    with pytest.raises(HTTPException):
        _create_mcp(admin, access={"no-such-module": "read"})
    with pytest.raises(HTTPException):
        _create_mcp(admin, access={"tasks": "everything"})
    with pytest.raises(HTTPException):  # grants nothing
        _create_mcp(admin, access={})
    with pytest.raises(HTTPException):
        _create_mcp(admin, expires_days=7)
    with pytest.raises(HTTPException):  # integration needs a target
        admin_create_api_key(
            ApiKeyCreateRequest(kind="integration", name="x", current_password="password123"),
            admin,
            None,
        )


def test_create_update_and_revoke_are_audited(admin):
    meta = _create_mcp(admin)["meta"]
    admin_update_api_key(meta["id"], ApiKeyUpdateRequest(name="Renamed"), admin, None)
    admin_revoke_api_key(meta["id"], admin, None)
    actions = [e["action"] for e in audit_log.list_entries(10)]
    assert {"api_key.create", "api_key.update", "api_key.revoke"} <= set(actions)


# --- MCP keys ------------------------------------------------------------------


def test_mcp_key_resolves_to_owner_with_key_context(admin):
    key = _create_mcp(admin)["key"]
    user = _use(key)
    assert user["id"] == admin["id"]
    assert user["_workspace"] == "personal"
    assert user["_api_key"]["access"] == {"tasks": "read"}
    assert "disabled_modules" in user


def test_wrong_secret_and_garbage_are_rejected(admin):
    key = _create_mcp(admin)["key"]
    for bad in (key[:-2] + "xx", "lcos_", "lcos_abc", "not-a-key", ""):
        with pytest.raises(HTTPException) as exc:
            _use(bad)
        assert exc.value.status_code == 401


def test_kinds_cannot_cross_routes(admin):
    mcp_key = _create_mcp(admin)["key"]
    lead_key = _create_integration(admin)["key"]
    with pytest.raises(HTTPException) as exc:
        _use(mcp_key, "leads:create")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        _use(lead_key, "mcp")
    assert exc.value.status_code == 403


def test_revoked_key_stops_working(admin):
    result = _create_mcp(admin)
    admin_revoke_api_key(result["meta"]["id"], admin, None)
    with pytest.raises(HTTPException) as exc:
        _use(result["key"])
    assert exc.value.status_code == 401


def test_expired_key_stops_working(admin):
    result = _create_mcp(admin, expires_days=30)

    def _expire(current):
        current["keys"][0]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        return current

    update_json(api_key_service._path(), _expire)
    with pytest.raises(HTTPException):
        _use(result["key"])
    assert api_key_service.list_keys()[0]["status"] == "expired"


def test_instance_switch_off_rejects_every_key(admin):
    key = _create_mcp(admin)["key"]
    update_admin_settings(AdminSettingsRequest(api_keys_enabled=False), admin, None)
    with pytest.raises(HTTPException):
        _use(key)
    with pytest.raises(HTTPException) as exc:
        _create_mcp(admin)
    assert exc.value.status_code == 409
    update_admin_settings(AdminSettingsRequest(api_keys_enabled=True), admin, None)
    assert _use(key)["id"] == admin["id"]


def test_session_path_refuses_api_keys(admin):
    key = _create_mcp(admin)["key"]
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    with pytest.raises(HTTPException) as exc:
        get_current_user(request, _creds(key), "personal")
    assert exc.value.status_code == 401
    assert "API keys" in exc.value.detail


def test_demoted_owner_mcp_key_stops_working(admin):
    key = _create_mcp(admin)["key"]
    auth_service.create_user("other@example.com", "password123", "Other", role="admin")
    auth_service.update_user_role(admin["id"], "member")
    with pytest.raises(HTTPException) as exc:
        _use(key)
    assert exc.value.status_code == 401


def test_deleting_creator_revokes_mcp_keys_but_not_integration_keys(admin):
    mcp_key = _create_mcp(admin)["key"]
    lead_key = _create_integration(admin)["key"]
    auth_service.delete_user(admin["id"])
    statuses = {k["kind"]: k["status"] for k in api_key_service.list_keys()}
    assert statuses == {"mcp": "revoked", "integration": "active"}
    with pytest.raises(HTTPException):
        _use(mcp_key)
    assert _use(lead_key, "leads:create")["name"] == "_team"


def test_mcp_workspace_no_longer_available_is_forbidden(admin):
    key = _create_mcp(admin, workspace="business")["key"]
    assert _use(key)["_workspace"] == "business"
    auth_service.update_system_settings({"enabled_workspaces": ["personal"]})
    with pytest.raises(HTTPException) as exc:
        _use(key)
    assert exc.value.status_code == 403


def test_owner_disabled_modules_apply_to_mcp_key(admin):
    key = _create_mcp(admin)["key"]
    auth_service.update_user(admin["id"], {"disabled_modules": ["contacts"]})
    assert "contacts" in _use(key)["disabled_modules"]


def test_editing_access_takes_effect_on_next_request(admin):
    result = _create_mcp(admin)
    admin_update_api_key(
        result["meta"]["id"],
        ApiKeyUpdateRequest(access={"tasks": "write"}, tool_overrides={"delete_task": False}),
        admin,
        None,
    )
    key_meta = _use(result["key"])["_api_key"]
    assert key_meta["access"] == {"tasks": "write"}
    assert key_meta["tool_overrides"] == {"delete_task": False}


def test_integration_key_access_cannot_be_edited(admin):
    meta = _create_integration(admin)["meta"]
    with pytest.raises(HTTPException) as exc:
        admin_update_api_key(meta["id"], ApiKeyUpdateRequest(access={"tasks": "read"}), admin, None)
    assert exc.value.status_code == 400


def test_revoked_key_cannot_be_edited(admin):
    meta = _create_mcp(admin)["meta"]
    admin_revoke_api_key(meta["id"], admin, None)
    with pytest.raises(HTTPException):
        admin_update_api_key(meta["id"], ApiKeyUpdateRequest(name="back"), admin, None)


# --- integration keys --------------------------------------------------------------


def test_integration_key_is_an_instance_principal_not_a_user(admin):
    meta = _create_integration(admin, target="_household")["meta"]
    assert meta["user_id"] is None and meta["workspace"] == "personal"
    principal = _use(_create_integration(admin)["key"], "leads:create")
    assert principal["role"] == "integration"
    assert principal["name"] == "_team" and principal["_workspace"] == "business"


def test_integration_key_survives_creator_demotion(admin):
    key = _create_integration(admin)["key"]
    auth_service.create_user("other@example.com", "password123", "Other", role="admin")
    auth_service.update_user_role(admin["id"], "member")
    assert _use(key, "leads:create")["name"] == "_team"


def test_integration_key_refused_when_its_workspace_is_off(admin):
    key = _create_integration(admin, target="_team")["key"]
    auth_service.update_system_settings({"enabled_workspaces": ["personal"]})
    with pytest.raises(HTTPException) as exc:
        _use(key, "leads:create")
    assert exc.value.status_code == 403


# --- limits & bookkeeping ---------------------------------------------------------


def test_per_key_rate_limit(admin):
    key = _create_mcp(admin)["key"]
    dep = require_api_key("mcp", max_calls=3, window_seconds=60)
    for _ in range(3):
        dep(_creds(key))
    with pytest.raises(HTTPException) as exc:
        dep(_creds(key))
    assert exc.value.status_code == 429


def test_last_used_is_recorded(admin):
    key = _create_mcp(admin)["key"]
    assert api_key_service.list_keys()[0]["last_used_at"] is None
    _use(key)
    assert api_key_service.list_keys()[0]["last_used_at"] is not None


def test_active_key_cap(admin, monkeypatch):
    monkeypatch.setattr(api_key_service, "MAX_ACTIVE_KEYS", 2)
    _create_mcp(admin)
    _create_integration(admin)
    with pytest.raises(HTTPException):
        _create_mcp(admin)
