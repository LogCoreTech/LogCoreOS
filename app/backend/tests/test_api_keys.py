"""Integrations & MCP keys (services/api_key_service.py, routers/auth/api_keys.py,
routers/auth/deps.py:require_api_key; docs/MEMORY.md 2026-10-25).

- integration keys: instance-owned, pinned to a shared list, the admin gets the
  key once, they survive their creator.
- MCP keys: an admin invites a chosen user (any role) with picked tools; the
  user is notified and accepts with their password, which is the ONLY moment
  the key exists in plaintext — the admin never sees it. Widening an accepted
  key's tools needs the user's approval; narrowing applies at once. Users can
  request access and revoke their own keys, never create or change one.

Plus the shared guarantees: hash-only storage, the session path refusing a
key outright, kinds can't cross routes, revoke/expiry/instance switch,
workspace re-validation, per-key rate limit."""

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
    ApiKeyAcceptRequest,
    ApiKeyAccessRequest,
    ApiKeyChangeResponse,
    ApiKeyCreateRequest,
    ApiKeyUpdateRequest,
    accept_my_api_key,
    admin_create_api_key,
    admin_dismiss_key_request,
    admin_list_api_keys,
    admin_revoke_api_key,
    admin_update_api_key,
    decline_my_api_key,
    my_api_keys,
    request_mcp_access,
    respond_my_api_key_change,
    revoke_my_api_key,
    update_admin_settings,
)
from routers.auth.deps import get_current_user, require_api_key
from services import api_key_service, audit_log, auth_service
from services import rate_limiter as rl
from services.file_service import read_json, update_json
from services.suggestions_service import get_notifications

PW = "password123"


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    rl._hits.clear()
    api_key_service._last_used_written.clear()
    yield
    rl._hits.clear()


@pytest.fixture()
def admin(brain):
    user = auth_service.create_user("admin@example.com", PW, "Admin", role="admin")
    # What get_current_user() grants a real admin request (every enabled workspace).
    auth_service.update_user(user["id"], {"workspaces": ["personal", "business"]})
    return auth_service.get_user_by_id(user["id"])


@pytest.fixture()
def member(admin):
    user = auth_service.create_user("member@example.com", PW, "Member")
    auth_service.update_user(user["id"], {"workspaces": ["business"]})
    return auth_service.get_user_by_id(user["id"])


def _invite(admin, for_user, access=None, overrides=None, **kw):
    req = ApiKeyCreateRequest(
        kind="mcp",
        name=kw.pop("name", "Claude"),
        user_id=for_user["id"],
        workspace=kw.pop("workspace", for_user.get("workspaces", ["personal"])[0]),
        access={"tasks": "read"} if access is None else access,
        tool_overrides=overrides or {},
        current_password=kw.pop("current_password", PW),
        **kw,
    )
    return admin_create_api_key(req, admin, None)


def _accept(key_id, user, password=PW):
    return accept_my_api_key(key_id, ApiKeyAcceptRequest(current_password=password), user, None)


def _mcp_key(admin, for_user, **kw):
    meta = _invite(admin, for_user, **kw)["meta"]
    return meta["id"], _accept(meta["id"], for_user)["key"]


def _create_integration(admin, target="_team", **kw):
    req = ApiKeyCreateRequest(
        kind="integration",
        name=kw.pop("name", "Lead form"),
        target=target,
        current_password=kw.pop("current_password", PW),
        **kw,
    )
    return admin_create_api_key(req, admin, None)


def _creds(key: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=key)


def _use(key: str, scope: str = "mcp") -> dict:
    return require_api_key(scope)(_creds(key))


# --- integration keys --------------------------------------------------------------


def test_integration_key_is_shown_once_and_stored_as_a_hash(admin):
    result = _create_integration(admin)
    key = result["key"]
    assert key.startswith("lcos_")
    assert key.split("_", 2)[2] not in str(read_json(api_key_service._path()))
    assert "secret_hash" not in result["meta"]
    assert "secret_hash" not in str(admin_list_api_keys(admin, None))


def test_integration_key_is_an_instance_principal_not_a_user(admin):
    principal = _use(_create_integration(admin)["key"], "leads:create")
    assert principal["role"] == "integration"
    assert principal["name"] == "_team" and principal["_workspace"] == "business"


def test_integration_key_survives_creator_deletion(admin):
    key = _create_integration(admin)["key"]
    auth_service.create_user("other@example.com", PW, "Other", role="admin")
    auth_service.delete_user(admin["id"])
    assert _use(key, "leads:create")["name"] == "_team"


def test_integration_key_refused_when_its_workspace_is_off(admin):
    key = _create_integration(admin, target="_team")["key"]
    auth_service.update_system_settings({"enabled_workspaces": ["personal"]})
    with pytest.raises(HTTPException) as exc:
        _use(key, "leads:create")
    assert exc.value.status_code == 403


def test_create_requires_correct_password(admin, member):
    with pytest.raises(HTTPException) as exc:
        _create_integration(admin, current_password="wrong-password")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException):
        _invite(admin, member, current_password="wrong-password")
    assert api_key_service.list_keys() == []


# --- MCP invites ---------------------------------------------------------------------


def test_invite_gives_the_admin_no_key_and_notifies_the_user(admin, member):
    result = _invite(admin, member)
    assert result["key"] is None
    meta = result["meta"]
    assert meta["status"] == "pending" and meta["user_id"] == member["id"]
    stored = read_json(api_key_service._path())["keys"][0]
    assert stored["secret_hash"] is None  # nothing exists that the admin could see
    [notice] = get_notifications("Member")
    assert notice["action"] == {"type": "open_mcp_access", "key_id": meta["id"]}
    assert "lcos_" not in notice["title"] + notice["body"]


def test_pending_invite_cannot_authenticate(admin, member):
    key_id = _invite(admin, member)["meta"]["id"]
    with pytest.raises(HTTPException):
        _use(f"lcos_{key_id}_anything")


def test_user_sees_exactly_which_tools_before_accepting(admin, member):
    _invite(admin, member, access={"tasks": "read"}, overrides={"add_task": True})
    [key] = my_api_keys(member, None)["keys"]
    names = {t["name"] for t in key["granted_tools"]}
    assert "add_task" in names and "list_tasks" in names and "delete_task" not in names


def test_accept_needs_the_users_password_and_returns_the_key_once(admin, member):
    key_id = _invite(admin, member, expires_days=30)["meta"]["id"]
    with pytest.raises(HTTPException) as exc:
        _accept(key_id, member, password="wrong-password")
    assert exc.value.status_code == 400
    result = _accept(key_id, member)
    assert result["key"].startswith(f"lcos_{key_id}_")
    assert result["meta"]["status"] == "active" and result["meta"]["expires_at"]
    assert result["key"].split("_", 2)[2] not in str(read_json(api_key_service._path()))
    with pytest.raises(HTTPException) as exc:  # can't accept twice
        _accept(key_id, member)
    assert exc.value.status_code == 409


def test_only_the_invited_user_can_accept(admin, member):
    key_id = _invite(admin, member)["meta"]["id"]
    with pytest.raises(HTTPException) as exc:
        _accept(key_id, admin)
    assert exc.value.status_code == 404


def test_member_key_acts_as_the_member(admin, member):
    _key_id, key = _mcp_key(admin, member)
    user = _use(key)
    assert user["id"] == member["id"] and user["role"] == "member"
    assert user["_workspace"] == "business"


def test_decline_and_expired_invites_cannot_be_accepted(admin, member):
    declined = _invite(admin, member)["meta"]["id"]
    decline_my_api_key(declined, member, None)
    with pytest.raises(HTTPException) as exc:
        _accept(declined, member)
    assert exc.value.status_code == 409

    stale = _invite(admin, member, name="Old")["meta"]["id"]

    def _age(data):
        for k in data["keys"]:
            if k["id"] == stale:
                k["invite_expires_at"] = (
                    datetime.now(timezone.utc) - timedelta(seconds=1)
                ).isoformat()
        return data

    update_json(api_key_service._path(), _age)
    assert api_key_service.get_key(stale)["status"] == "expired"
    with pytest.raises(HTTPException):
        _accept(stale, member)


def test_invite_rejects_a_workspace_the_user_cant_use(admin, member):
    with pytest.raises(HTTPException) as exc:
        _invite(admin, member, workspace="personal")
    assert exc.value.status_code == 400


def test_invite_needs_a_real_user_and_a_real_grant(admin, member):
    with pytest.raises(HTTPException):
        admin_create_api_key(
            ApiKeyCreateRequest(
                kind="mcp", name="x", access={"tasks": "read"}, current_password=PW
            ),
            admin,
            None,
        )
    with pytest.raises(HTTPException):
        _invite(admin, member, access={})
    with pytest.raises(HTTPException):
        _invite(admin, member, access={"no-such-module": "read"})


# --- changing an MCP key's tools ---------------------------------------------------------


def test_narrowing_applies_at_once(admin, member):
    key_id, key = _mcp_key(admin, member, access={"tasks": "write"})
    result = admin_update_api_key(
        key_id, ApiKeyUpdateRequest(access={"tasks": "read"}), admin, None
    )
    assert result["needs_approval"] is False
    assert _use(key)["_api_key"]["access"] == {"tasks": "read"}


def test_widening_waits_for_the_users_approval(admin, member):
    key_id, key = _mcp_key(admin, member, access={"tasks": "read"})
    result = admin_update_api_key(
        key_id, ApiKeyUpdateRequest(access={"tasks": "write"}), admin, None
    )
    assert result["needs_approval"] is True
    assert _use(key)["_api_key"]["access"] == {"tasks": "read"}  # old access stands
    [key_view] = my_api_keys(member, None)["keys"]
    assert "add_task" in {t["name"] for t in key_view["proposed_tools"]}
    assert any(
        n["title"] == "Review a change to your MCP access" for n in get_notifications("Member")
    )

    respond_my_api_key_change(key_id, ApiKeyChangeResponse(accept=True), member, None)
    assert _use(key)["_api_key"]["access"] == {"tasks": "write"}


def test_rejecting_a_widening_keeps_the_old_tools(admin, member):
    key_id, key = _mcp_key(admin, member, access={"tasks": "read"})
    admin_update_api_key(key_id, ApiKeyUpdateRequest(access={"tasks": "write"}), admin, None)
    respond_my_api_key_change(key_id, ApiKeyChangeResponse(accept=False), member, None)
    meta = _use(key)["_api_key"]
    assert meta["access"] == {"tasks": "read"} and meta["proposed_access"] is None


def test_editing_a_pending_invite_applies_directly(admin, member):
    key_id = _invite(admin, member, access={"tasks": "read"})["meta"]["id"]
    result = admin_update_api_key(
        key_id, ApiKeyUpdateRequest(access={"tasks": "write"}), admin, None
    )
    assert result["needs_approval"] is False
    assert result["meta"]["access"] == {"tasks": "write"}


def test_integration_key_has_no_tools_to_change(admin):
    meta = _create_integration(admin)["meta"]
    with pytest.raises(HTTPException) as exc:
        admin_update_api_key(meta["id"], ApiKeyUpdateRequest(access={"tasks": "read"}), admin, None)
    assert exc.value.status_code == 400


# --- revocation & lifecycle -------------------------------------------------------------


def test_user_can_revoke_their_own_key_but_not_someone_elses(admin, member):
    key_id, key = _mcp_key(admin, member)
    with pytest.raises(HTTPException) as exc:
        revoke_my_api_key(key_id, admin, None)
    assert exc.value.status_code == 404
    revoke_my_api_key(key_id, member, None)
    with pytest.raises(HTTPException):
        _use(key)


def test_admin_revoke_works_on_pending_and_active(admin, member):
    pending = _invite(admin, member)["meta"]["id"]
    admin_revoke_api_key(pending, admin, None)
    with pytest.raises(HTTPException):
        _accept(pending, member)
    key_id, key = _mcp_key(admin, member, name="Second")
    admin_revoke_api_key(key_id, admin, None)
    with pytest.raises(HTTPException) as exc:
        _use(key)
    assert exc.value.status_code == 401


def test_deleting_a_user_revokes_their_mcp_keys(admin, member):
    _key_id, key = _mcp_key(admin, member)
    lead_key = _create_integration(admin)["key"]
    auth_service.delete_user(member["id"])
    with pytest.raises(HTTPException):
        _use(key)
    assert _use(lead_key, "leads:create")["name"] == "_team"


def test_expired_key_stops_working(admin, member):
    key_id, key = _mcp_key(admin, member, expires_days=30)

    def _expire(data):
        for k in data["keys"]:
            if k["id"] == key_id:
                k["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        return data

    update_json(api_key_service._path(), _expire)
    with pytest.raises(HTTPException):
        _use(key)


def test_mcp_workspace_no_longer_available_is_forbidden(admin):
    _key_id, key = _mcp_key(admin, admin, workspace="business")
    auth_service.update_system_settings({"enabled_workspaces": ["personal"]})
    with pytest.raises(HTTPException) as exc:
        _use(key)
    assert exc.value.status_code == 403


def test_users_disabled_modules_apply_to_their_key(admin, member):
    _key_id, key = _mcp_key(admin, member)
    auth_service.update_user(member["id"], {"disabled_modules": ["contacts"]})
    assert "contacts" in _use(key)["disabled_modules"]


# --- requests ---------------------------------------------------------------------------


def test_request_notifies_admins_once_and_an_invite_handles_it(admin, member):
    request_mcp_access(ApiKeyAccessRequest(note="for my laptop"), member, None)
    assert any(n["title"] == "MCP access requested" for n in get_notifications("Admin"))
    assert my_api_keys(member, None)["has_open_request"] is True
    with pytest.raises(HTTPException) as exc:
        request_mcp_access(ApiKeyAccessRequest(), member, None)
    assert exc.value.status_code == 409
    [req] = admin_list_api_keys(admin, None)["requests"]
    assert req["note"] == "for my laptop"
    _invite(admin, member)
    assert admin_list_api_keys(admin, None)["requests"] == []


def test_admin_can_dismiss_a_request(admin, member):
    request_mcp_access(ApiKeyAccessRequest(), member, None)
    [req] = api_key_service.list_requests()
    admin_dismiss_key_request(req["id"], admin, None)
    assert api_key_service.list_requests() == []
    assert my_api_keys(member, None)["has_open_request"] is False


# --- shared guarantees ---------------------------------------------------------------------


def test_session_path_refuses_api_keys(admin, member):
    _key_id, key = _mcp_key(admin, member)
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    with pytest.raises(HTTPException) as exc:
        get_current_user(request, _creds(key), "personal")
    assert exc.value.status_code == 401
    assert "API keys" in exc.value.detail


def test_kinds_cannot_cross_routes(admin, member):
    _key_id, mcp_key = _mcp_key(admin, member)
    lead_key = _create_integration(admin)["key"]
    with pytest.raises(HTTPException) as exc:
        _use(mcp_key, "leads:create")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        _use(lead_key, "mcp")
    assert exc.value.status_code == 403


def test_wrong_secret_and_garbage_are_rejected(admin, member):
    _key_id, key = _mcp_key(admin, member)
    for bad in (key[:-2] + "xx", "lcos_", "lcos_abc", "not-a-key", ""):
        with pytest.raises(HTTPException) as exc:
            _use(bad)
        assert exc.value.status_code == 401


def test_instance_switch_off_blocks_keys_invites_accepts_and_requests(admin, member):
    pending = _invite(admin, member, name="Later")["meta"]["id"]
    _key_id, key = _mcp_key(admin, member)
    update_admin_settings(AdminSettingsRequest(api_keys_enabled=False), admin, None)
    with pytest.raises(HTTPException):
        _use(key)
    for blocked in (
        lambda: _create_integration(admin),
        lambda: _accept(pending, member),
        lambda: request_mcp_access(ApiKeyAccessRequest(), member, None),
    ):
        with pytest.raises(HTTPException) as exc:
            blocked()
        assert exc.value.status_code == 409
    update_admin_settings(AdminSettingsRequest(api_keys_enabled=True), admin, None)
    assert _use(key)["id"] == member["id"]


def test_every_step_is_audited(admin, member):
    key_id, _key = _mcp_key(admin, member)
    admin_update_api_key(key_id, ApiKeyUpdateRequest(access={"tasks": "write"}), admin, None)
    respond_my_api_key_change(key_id, ApiKeyChangeResponse(accept=True), member, None)
    revoke_my_api_key(key_id, member, None)
    actions = {e["action"] for e in audit_log.list_entries(20)}
    assert {
        "api_key.invite",
        "api_key.accept",
        "api_key.change_proposed",
        "api_key.change_accept",
        "api_key.revoke",
    } <= actions


def test_per_key_rate_limit(admin, member):
    _key_id, key = _mcp_key(admin, member)
    dep = require_api_key("mcp", max_calls=3, window_seconds=60)
    for _ in range(3):
        dep(_creds(key))
    with pytest.raises(HTTPException) as exc:
        dep(_creds(key))
    assert exc.value.status_code == 429


def test_last_used_is_recorded(admin, member):
    key_id, key = _mcp_key(admin, member)
    assert api_key_service.get_key(key_id)["last_used_at"] is None
    _use(key)
    assert api_key_service.get_key(key_id)["last_used_at"] is not None


def test_key_cap_counts_pending_invites(admin, member, monkeypatch):
    monkeypatch.setattr(api_key_service, "MAX_ACTIVE_KEYS", 2)
    _invite(admin, member)
    _create_integration(admin)
    with pytest.raises(HTTPException):
        _invite(admin, member, name="Third")
