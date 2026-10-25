"""MCP server (services/mcp_service.py + routers/mcp.py). Keys are real
(api_key_service) and resolved through the real require_api_key() chain, and
tools run against the real agent registry on the `brain` fixture — so these
also prove the read/write/admin/chat-only filtering against the registry as it
actually is, not a hand-copied list."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from routers.auth.deps import require_api_key
from routers.mcp import mcp_no_stream, mcp_post
from services import api_key_service, audit_log, auth_service, mcp_service
from services import rate_limiter as rl


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    rl._hits.clear()
    yield
    rl._hits.clear()


@pytest.fixture()
def admin(brain):
    user = auth_service.create_user("owner@example.com", "password123", "Owner", role="admin")
    auth_service.update_user(user["id"], {"workspaces": ["personal", "business"]})
    return auth_service.get_user_by_id(user["id"])


def _everything(level):
    return {g["id"]: level for g in mcp_service.catalog()}


def _key_user(admin, access=None, overrides=None):
    _meta, key = api_key_service.create_key(
        admin,
        "mcp",
        "Claude",
        None,
        workspace="personal",
        access=_everything("read") if access is None else access,
        tool_overrides=overrides or {},
    )
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=key)
    return require_api_key("mcp")(creds)


def _rpc(user, method, params=None, msg_id=1):
    msg = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        msg["params"] = params
    return mcp_service.handle_message(msg, user)


def _tool_names(user):
    return {t["name"] for t in _rpc(user, "tools/list")["result"]["tools"]}


# --- protocol ---------------------------------------------------------------


def test_initialize_negotiates_version(admin):
    user = _key_user(admin)
    res = _rpc(user, "initialize", {"protocolVersion": "2025-03-26"})["result"]
    assert res["protocolVersion"] == "2025-03-26"
    assert res["capabilities"] == {"tools": {"listChanged": False}}
    assert res["serverInfo"]["name"] == "LogCoreOS"
    unknown = _rpc(user, "initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert unknown["protocolVersion"] == mcp_service.SUPPORTED_PROTOCOL_VERSIONS[0]


def test_notifications_get_no_response(admin):
    user = _key_user(admin)
    msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert mcp_service.handle_message(msg, user) is None


def test_ping_unknown_method_and_bad_messages(admin):
    user = _key_user(admin)
    assert _rpc(user, "ping")["result"] == {}
    assert _rpc(user, "resources/list")["error"]["code"] == mcp_service.METHOD_NOT_FOUND
    bad = mcp_service.handle_message({"id": 1, "method": "ping"}, user)
    assert bad["error"]["code"] == mcp_service.INVALID_REQUEST
    assert _rpc(user, "tools/call", {"name": 5})["error"]["code"] == mcp_service.INVALID_PARAMS


# --- tool filtering -----------------------------------------------------------


def test_read_key_sees_only_read_tools(admin):
    user = _key_user(admin)
    tools = _rpc(user, "tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"list_tasks", "get_priorities"} <= names
    assert "add_task" not in names and "create_brain_file" not in names
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    assert all("inputSchema" in t for t in tools)


def test_write_key_adds_write_tools(admin):
    names = _tool_names(_key_user(admin, access=_everything("write")))
    assert {"list_tasks", "add_task", "create_brain_file"} <= names


def test_admin_chat_only_and_metered_tools_never_exposed(admin):
    names = _tool_names(_key_user(admin, access=_everything("write")))
    for blocked in (
        "list_users",
        "read_system_file",
        "update_system_file",
        "run_tests",
        "propose_plan",
        "ask_user_question",
        "run_suggestion",
        "search_web",
    ):
        assert blocked not in names
    from module_registry import admin_agent_tool_names

    assert not names & admin_agent_tool_names()


def test_disabled_module_tools_hidden_and_refused(admin):
    auth_service.update_user(admin["id"], {"disabled_modules": ["tasks"]})
    user = _key_user(admin, access=_everything("write"))
    assert "list_tasks" not in _tool_names(user)
    res = _rpc(user, "tools/call", {"name": "list_tasks", "arguments": {}})
    assert res["error"]["code"] == mcp_service.INVALID_PARAMS


def test_read_key_cannot_call_write_tool(admin):
    user = _key_user(admin)
    res = _rpc(user, "tools/call", {"name": "add_task", "arguments": {"title": "x"}})
    assert res["error"]["code"] == mcp_service.INVALID_PARAMS
    from services.file_service import tasks_path

    assert not tasks_path("Owner").exists()


# --- calling tools --------------------------------------------------------------


def test_write_then_read_round_trip(admin):
    user = _key_user(admin, access=_everything("write"))
    added = _rpc(
        user,
        "tools/call",
        {"name": "add_task", "arguments": {"title": "Call back lead", "category": "Work"}},
    )["result"]
    assert added["isError"] is False
    listed = _rpc(user, "tools/call", {"name": "list_tasks", "arguments": {}})["result"]
    assert "Call back lead" in listed["content"][0]["text"]
    json.loads(listed["content"][0]["text"])  # tool output is valid JSON text


def test_write_calls_are_audited_reads_are_not(admin):
    user = _key_user(admin, access=_everything("write"))
    _rpc(user, "tools/call", {"name": "list_tasks", "arguments": {}})
    _rpc(user, "tools/call", {"name": "add_task", "arguments": {"title": "t", "category": "c"}})
    entries = [e for e in audit_log.list_entries(20) if e["action"] == "api_key.mcp_write"]
    assert [e["target"] for e in entries] == ["add_task"]
    assert entries[0]["details"]["key_name"] == "Claude"


def test_tool_error_sets_is_error(admin):
    user = _key_user(admin, access=_everything("write"))
    res = _rpc(user, "tools/call", {"name": "read_brain_file", "arguments": {"path": "../x.md"}})
    assert res["result"]["isError"] is True


# --- origin guard ---------------------------------------------------------------


def test_origin_guard(brain, monkeypatch):
    from services import hosting_service

    assert mcp_service.origin_allowed("") is True
    assert mcp_service.origin_allowed("https://evil.example") is False
    monkeypatch.setattr(hosting_service, "effective_domain_url", lambda: "https://os.example.com")
    assert mcp_service.origin_allowed("https://os.example.com/") is True
    assert mcp_service.origin_allowed("https://evil.example") is False


# --- HTTP layer -----------------------------------------------------------------


def _request(body: bytes, headers: dict | None = None) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {"type": "http", "method": "POST", "path": "/api/v1/mcp", "headers": raw_headers}
    return Request(scope, receive)


def _post(user, payload, headers=None, version=""):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return asyncio.run(mcp_post(_request(body, headers), user, None, version))


def test_http_request_notification_batch_and_parse_error(admin):
    user = _key_user(admin)
    ok = _post(user, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert ok.status_code == 200 and json.loads(ok.body)["result"] == {}
    note = _post(user, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert note.status_code == 202
    batch = _post(
        user,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ],
    )
    assert [r["id"] for r in json.loads(batch.body)] == [1, 2]
    bad = _post(user, b"{not json")
    assert bad.status_code == 400
    assert json.loads(bad.body)["error"]["code"] == mcp_service.PARSE_ERROR


def test_http_rejects_foreign_origin_and_unknown_protocol_version(admin):
    user = _key_user(admin)
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    with pytest.raises(HTTPException) as exc:
        _post(user, ping, headers={"Origin": "https://evil.example"})
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        _post(user, ping, version="2020-01-01")
    assert exc.value.status_code == 400
    assert _post(user, ping, version="2025-06-18").status_code == 200


def test_get_is_405():
    assert mcp_no_stream(None).status_code == 405


def test_integration_key_is_refused(admin):
    _meta, key = api_key_service.create_key(admin, "integration", "form", None, target="_team")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=key)
    with pytest.raises(HTTPException) as exc:
        require_api_key("mcp")(creds)
    assert exc.value.status_code == 403


# --- per-key access -------------------------------------------------------------


def test_module_level_access_limits_to_that_module(admin):
    user = _key_user(admin, access={"tasks": "read"})
    names = _tool_names(user)
    assert "list_tasks" in names
    assert "add_task" not in names
    assert "get_priorities" not in names  # core group not granted


def test_override_adds_one_write_tool_to_a_read_group(admin):
    user = _key_user(admin, access={"tasks": "read"}, overrides={"add_task": True})
    names = _tool_names(user)
    assert {"list_tasks", "add_task"} <= names
    assert "delete_task" not in names


def test_override_removes_one_tool_from_a_write_group(admin):
    user = _key_user(admin, access={"tasks": "write"}, overrides={"delete_task": False})
    names = _tool_names(user)
    assert "add_task" in names and "delete_task" not in names
    res = _rpc(user, "tools/call", {"name": "delete_task", "arguments": {"task_id": "x"}})
    assert res["error"]["code"] == mcp_service.INVALID_PARAMS


def test_override_alone_can_grant_a_single_tool(admin):
    user = _key_user(admin, access={}, overrides={"add_task": True})
    assert _tool_names(user) == {"add_task"}


def test_catalog_never_offers_admin_chat_only_or_metered_tools(brain):
    offered = {t["name"] for g in mcp_service.catalog() for t in g["tools"]}
    for blocked in ("list_users", "run_tests", "propose_plan", "ask_user_question", "search_web"):
        assert blocked not in offered
    groups = [g["id"] for g in mcp_service.catalog()]
    assert groups[0] == "core" and "tasks" in groups


def test_access_validation_rejects_unknown_and_empty(brain):
    with pytest.raises(ValueError):
        mcp_service.validate_access({"nope": "read"}, {})
    with pytest.raises(ValueError):
        mcp_service.validate_access({}, {"list_users": True})  # admin tool: not grantable
    with pytest.raises(ValueError):
        mcp_service.validate_access({"tasks": "none"}, {})
    access, overrides = mcp_service.validate_access({"tasks": "read", "core": "none"}, {})
    assert access == {"tasks": "read"} and overrides == {}
