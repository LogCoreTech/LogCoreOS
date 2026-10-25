"""Minimal MCP (Model Context Protocol) server over Streamable HTTP — the
transport-independent half. routers/mcp.py is the thin HTTP layer.

Exposes the SAME tool registry the in-app AI agent uses (agent_service), so
every module's agent tools become available to an outside MCP client (Claude
Desktop, Claude Code, any MCP-capable app) without a second implementation:
`_get_tools(user)` already hides disabled/uninstalled modules' tools, and
`_execute_tool(...)` already enforces each tool's own access checks and never
raises.

Hand-rolled rather than the `mcp` Python SDK: the SDK needs a newer pydantic
than this app pins, and the slice of the protocol a tools-only, stateless
server needs is small — initialize, ping, tools/list, tools/call, and the
initialized notification. JSON responses only, no SSE stream and no session
id (both optional in the spec for a server that never pushes).

Per-key access on top of the registry (api_key_service, kind "mcp") is set
PER WORKSPACE: `grants: {workspace: {"access": {group: "read"|"write"},
"tool_overrides": {tool_name: bool}}}`. A group is a module id, or "core" for
the agent's own built-in tools (Brain files, profile, memory, notifications);
"read" allows only the group's tools the agent itself treats as read-only
(agent_service._READ_TOOLS + modules' read_only_agent_tools), "write" the
whole group, and an override switches one tool on or off regardless. A group
setting covers tools a module adds later; an override names one tool. Every
exposed tool gets an extra `workspace` argument listing exactly the
workspaces it's allowed in for this key (required when more than one), and
each call runs with that workspace's own data and module access. In-app the
agent pauses writes for approval; over MCP that approval belongs to the
client app (which asks before each call), and every write call is
audit-logged here.

Never exposed, whatever a key says: admin tools (core _ADMIN_TOOLS and
modules' admin_agent_tools — a key must not be an admin console), the
chat-only pause/resume tools, and tools that spend the instance's paid AI or
web-search allowance on someone else's behalf.
"""

import json
import logging
from typing import Any

logger = logging.getLogger("logcore.mcp")

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26")
SERVER_NAME = "LogCoreOS"

# Chat-only control flow (they pause the in-app agent loop and mean nothing
# to an outside client) and tools that spend the instance's metered AI or
# web-search budget.
_NEVER_EXPOSED = {"propose_plan", "ask_user_question", "run_suggestion", "search_web"}

_INSTRUCTIONS = (
    "Tools for this person's LogCoreOS instance — tasks, notes, contacts, calendar, "
    "and whatever other modules they have enabled. Every tool acts as the person who "
    "created this API key, limited to the tools and workspace the key was given."
)

# JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def _read_tool_names() -> set[str]:
    from module_registry import read_only_agent_tool_names
    from services.agent_service import _READ_TOOLS

    return set(_READ_TOOLS) | read_only_agent_tool_names()


def _admin_tool_names() -> set[str]:
    from module_registry import admin_agent_tool_names
    from services.agent_tool_schemas import _ADMIN_TOOLS

    return {t["name"] for t in _ADMIN_TOOLS} | admin_agent_tool_names()


CORE_GROUP = "core"
ACCESS_LEVELS = ("read", "write")
WORKSPACES = ("business", "personal")


def _exposable(names: set[str]) -> set[str]:
    return names - _NEVER_EXPOSED - _admin_tool_names()


def catalog() -> list[dict]:
    """Every tool an MCP key could be granted, grouped for the Admin →
    Integrations & MCP picker: [{id, label, tools: [{name, description,
    read_only}]}]. Core tools first, then each ACTIVE module's own tools. The
    picker narrows this per person and workspace (their own disabled
    modules); `allowed_tools()` applies the same cut at call time, plus
    config-dependent drops (e.g. Home Assistant not configured)."""
    from module_registry import active_manifests
    from services.agent_service import _module_tool_schemas
    from services.agent_tool_schemas import _USER_TOOLS

    read_names = _read_tool_names()

    def _entry(t: dict) -> dict:
        return {
            "name": t["name"],
            "description": t.get("description", ""),
            "read_only": t["name"] in read_names,
        }

    core_names = _exposable({t["name"] for t in _USER_TOOLS})
    groups = [
        {
            "id": CORE_GROUP,
            "label": "Brain & profile",
            "tools": [_entry(t) for t in _USER_TOOLS if t["name"] in core_names],
        }
    ]
    schemas = {t["name"]: t for t in _module_tool_schemas()}
    for module_id, manifest in sorted(
        active_manifests().items(), key=lambda kv: kv[1].display_name.lower()
    ):
        names = _exposable(set(manifest.owned_agent_tools))
        tools = [
            _entry(schemas[n]) for n in manifest.owned_agent_tools if n in names and n in schemas
        ]
        if tools:
            groups.append({"id": module_id, "label": manifest.display_name, "tools": tools})
    return groups


def _tool_groups() -> dict[str, str]:
    """{tool_name: group_id} for every module-owned tool; anything else is core."""
    from module_registry import discover_manifests

    manifests, _errors = discover_manifests()
    return {
        name: module_id
        for module_id, manifest in manifests.items()
        for name in manifest.owned_agent_tools
    }


def _tool_allowed(
    name: str, group: str, read_names: set[str], access: dict, overrides: dict
) -> bool:
    if name in overrides:
        return overrides[name]
    level = access.get(group)
    return level == "write" or (level == "read" and name in read_names)


def _clean_grant(grant: dict, groups: dict, known: set[str]) -> tuple[dict, dict]:
    clean_access: dict[str, str] = {}
    for group, level in ((grant or {}).get("access") or {}).items():
        if level in (None, "", "none"):
            continue
        if group not in groups:
            raise ValueError(f"Unknown tool group: {group!r}")
        if level not in ACCESS_LEVELS:
            raise ValueError(f"Access for {group!r} must be read, write, or none")
        clean_access[group] = level
    clean_overrides: dict[str, bool] = {}
    for name, allowed in ((grant or {}).get("tool_overrides") or {}).items():
        if name not in known:
            raise ValueError(f"Unknown or non-grantable tool: {name!r}")
        clean_overrides[name] = bool(allowed)
    return clean_access, clean_overrides


def validate_grants(grants: dict, allowed_workspaces: list[str]) -> dict:
    """Clean + validate per-workspace grants against the live catalog and the
    person's own workspaces. Drops workspaces that grant nothing; raises
    ValueError for anything unknown, or if nothing at all is granted."""
    groups = {g["id"]: g for g in catalog()}
    known = {t["name"] for g in groups.values() for t in g["tools"]}
    read_names = _read_tool_names()
    clean: dict[str, dict] = {}
    for workspace, grant in (grants or {}).items():
        if workspace not in allowed_workspaces:
            raise ValueError(f"This person can't use the {workspace!r} workspace")
        access, overrides = _clean_grant(grant, groups, known)
        if any(
            _tool_allowed(t["name"], g["id"], read_names, access, overrides)
            for g in groups.values()
            for t in g["tools"]
        ):
            clean[workspace] = {"access": access, "tool_overrides": overrides}
    if not clean:
        raise ValueError("Pick at least one tool this key can use")
    return clean


def granted_tools(grants: dict) -> list[dict]:
    """The catalog tools these grants allow, for showing a person exactly what
    they're agreeing to: [{name, description, read_only, group, label,
    workspace}]. Catalog-based (instance-wide), so it's the most the key could
    ever do — at call time it's further cut down to what the person can use."""
    read_names = _read_tool_names()
    groups = catalog()
    out = []
    for workspace, grant in (grants or {}).items():
        access = grant.get("access") or {}
        overrides = grant.get("tool_overrides") or {}
        out.extend(
            {**t, "group": g["id"], "label": g["label"], "workspace": workspace}
            for g in groups
            for t in g["tools"]
            if _tool_allowed(t["name"], g["id"], read_names, access, overrides)
        )
    return out


def _context(user: dict, workspace: str) -> dict:
    """The key's user as seen from one workspace — require_api_key computed
    each usable workspace's disabled modules into `_mcp_workspaces`."""
    return {
        **user,
        "_workspace": workspace,
        "disabled_modules": user["_mcp_workspaces"][workspace],
    }


def _allowed_by_workspace(user: dict) -> dict[str, tuple[dict, list[str]]]:
    """{tool_name: (schema, [workspaces it's allowed in])}, in the agent's own
    tool order: per granted workspace, what the person can use there right now
    (`_get_tools` — that workspace's disabled modules gone), minus
    never-exposed tools, filtered by the key's grant for that workspace."""
    from services.agent_service import _get_tools
    from services.api_key_service import grants_of

    grants = grants_of(user.get("_api_key", {}))
    read_names = _read_tool_names()
    groups = _tool_groups()
    blocked = _NEVER_EXPOSED | _admin_tool_names()
    out: dict[str, tuple[dict, list[str]]] = {}
    for workspace in user.get("_mcp_workspaces", {}):
        grant = grants.get(workspace)
        if not grant:
            continue
        for tool in _get_tools(_context(user, workspace)):
            name = tool["name"]
            if name in blocked or not _tool_allowed(
                name,
                groups.get(name, CORE_GROUP),
                read_names,
                grant.get("access") or {},
                grant.get("tool_overrides") or {},
            ):
                continue
            out.setdefault(name, (tool, []))[1].append(workspace)
    return out


def allowed_tools(user: dict) -> list[dict]:
    """The tool schemas this key may see/call (without the added `workspace`
    argument — see `_mcp_tool`)."""
    return [tool for tool, _ws in _allowed_by_workspace(user).values()]


def _mcp_tool(tool: dict, workspaces: list[str], read_names: set[str]) -> dict:
    """MCP view of one tool, with a `workspace` argument added listing exactly
    the workspaces this key may use it in (required when there's a choice)."""
    is_read = tool["name"] in read_names
    schema = dict(tool.get("input_schema") or {"type": "object", "properties": {}})
    properties = dict(schema.get("properties") or {})
    properties["workspace"] = {
        "type": "string",
        "enum": workspaces,
        "description": (
            "Which LogCore workspace to act in: 'business' (work data, Team) or "
            "'personal' (personal data, Household). Data is separate in each."
            + ("" if len(workspaces) > 1 else f" Only '{workspaces[0]}' is allowed for this key.")
        ),
    }
    schema["properties"] = properties
    required = [r for r in schema.get("required") or [] if r != "workspace"]
    if len(workspaces) > 1:
        required.append("workspace")
    schema["required"] = required
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "inputSchema": schema,
        "annotations": {"readOnlyHint": is_read, "destructiveHint": not is_read},
    }


def _result(msg_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle_message(message: Any, user: dict) -> dict | None:
    """Handle one JSON-RPC message. Returns the response, or None for a
    notification (no `id`), which per spec gets no response body."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "Not a JSON-RPC 2.0 message")
    method = message.get("method")
    msg_id = message.get("id")
    is_notification = "id" not in message
    if not isinstance(method, str):
        # A client's response to a server request — this server never sends any.
        return None if is_notification else _error(msg_id, INVALID_REQUEST, "Missing method")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return (
            None if is_notification else _error(msg_id, INVALID_PARAMS, "params must be an object")
        )

    if is_notification:
        # notifications/initialized, notifications/cancelled, … — nothing to do
        # for a stateless server that never runs anything in the background.
        return None

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = (
            requested
            if requested in SUPPORTED_PROTOCOL_VERSIONS
            else SUPPORTED_PROTOCOL_VERSIONS[0]
        )
        from services.update_service import get_installed_version

        return _result(
            msg_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": get_installed_version()},
                "instructions": _INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        read_names = _read_tool_names()
        return _result(
            msg_id,
            {
                "tools": [
                    _mcp_tool(tool, workspaces, read_names)
                    for tool, workspaces in _allowed_by_workspace(user).values()
                ]
            },
        )
    if method == "tools/call":
        return _call_tool(msg_id, params, user)
    return _error(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")


def _call_tool(msg_id: Any, params: dict, user: dict) -> dict:
    from services import audit_log
    from services.agent_service import _execute_tool

    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return _error(msg_id, INVALID_PARAMS, "tools/call needs a name and an arguments object")
    entry = _allowed_by_workspace(user).get(name)
    if entry is None:
        # Same message whether the tool doesn't exist, belongs to a disabled
        # module, or is outside this key's grants — don't map the registry.
        return _error(msg_id, INVALID_PARAMS, f"Unknown tool or not allowed for this key: {name}")
    _tool, workspaces = entry
    arguments = dict(arguments)
    workspace = arguments.pop("workspace", None)
    if workspace is None:
        if len(workspaces) > 1:
            return _error(
                msg_id,
                INVALID_PARAMS,
                f"Say which workspace to use for {name}: one of {', '.join(workspaces)}",
            )
        workspace = workspaces[0]
    if workspace not in workspaces:
        return _error(
            msg_id,
            INVALID_PARAMS,
            f"{name} isn't allowed in the {workspace!r} workspace for this key "
            f"(allowed: {', '.join(workspaces)})",
        )

    acting = _context(user, workspace)
    if name not in _read_tool_names():
        key = user.get("_api_key", {})
        audit_log.record(
            user,
            "api_key.mcp_write",
            name,
            {"key_id": key.get("id"), "key_name": key.get("name"), "workspace": workspace},
        )
    output = _execute_tool(name, arguments, acting, workspace)
    is_error = isinstance(output, dict) and set(output) == {"error"}
    try:
        text = output if isinstance(output, str) else json.dumps(output, default=str)
    except (TypeError, ValueError):
        text = str(output)
    return _result(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error})


def origin_allowed(origin: str) -> bool:
    """DNS-rebinding guard the MCP spec requires of HTTP servers: a request
    carrying an Origin header (i.e. made by a browser page) must come from
    this instance's own configured origin. Desktop/CLI MCP clients send no
    Origin at all. Mirrors main.py's DynamicCORSMiddleware._is_allowed()
    (which a service can't import), minus its wildcard escape hatch."""
    if not origin:
        return True
    from config import settings
    from services.hosting_service import effective_domain_url

    domain = effective_domain_url()
    if domain:
        return origin.rstrip("/") == domain.rstrip("/")
    allowed = {o.strip().rstrip("/") for o in settings.allowed_origins.split(",") if o.strip()}
    return origin.rstrip("/") in allowed
