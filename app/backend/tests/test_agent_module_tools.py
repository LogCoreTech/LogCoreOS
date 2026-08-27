"""Enforcement-gap + integration tests for the AI agent's module-tool
plumbing: _get_tools() must hard-exclude a disabled module's tools (the model
can never even be offered a call that's guaranteed to fail), and
_execute_tool() must actually dispatch a real tool call through to an active
module's own agent_tools.py."""

from services import agent_service, mod_store_service

_MANIFEST_SRC = """
from module_registry import ModuleManifest

def _get_router():
    from module_packages.t_agent_tools.backend.router import router
    return router

MODULE = ModuleManifest(
    id="t_agent_tools",
    display_name="Test",
    description="Test",
    icon="x",
    version="0.0.1",
    router_prefix="/api/v1/t_agent_tools",
    router_tags=["t_agent_tools"],
    get_router=_get_router,
    owned_agent_tools=["t_ping_tool"],
)
"""

_AGENT_TOOLS_SRC = """
TOOL_SCHEMAS = [
    {
        "name": "t_ping_tool",
        "description": "A fake test tool.",
        "input_schema": {"type": "object", "properties": {}},
    }
]

def execute(name, inputs, user, workspace="personal"):
    if name != "t_ping_tool":
        return None
    return {"pong": True, "for_user": user["name"]}
"""


def _user(name: str, disabled_modules: list[str], role: str = "member") -> dict:
    return {"name": name, "disabled_modules": disabled_modules, "role": role}


def test_get_tools_excludes_disabled_module_tool(fake_module, brain):
    fake_module("t_agent_tools", _MANIFEST_SRC, agent_tools_src=_AGENT_TOOLS_SRC)
    mod_store_service.mark_installed("t_agent_tools", by="tester")

    tools = agent_service._get_tools(_user("alice", ["t_agent_tools"]))
    assert "t_ping_tool" not in {t["name"] for t in tools}


def test_get_tools_includes_enabled_module_tool(fake_module, brain):
    fake_module("t_agent_tools", _MANIFEST_SRC, agent_tools_src=_AGENT_TOOLS_SRC)
    mod_store_service.mark_installed("t_agent_tools", by="tester")

    tools = agent_service._get_tools(_user("alice", []))
    assert "t_ping_tool" in {t["name"] for t in tools}


def test_get_tools_excludes_not_installed_module_tool(fake_module, brain):
    fake_module("t_agent_tools", _MANIFEST_SRC, agent_tools_src=_AGENT_TOOLS_SRC)
    # deliberately never installed — active_manifests() excludes it, so
    # _module_tool_schemas() never even offers it regardless of disabled_modules
    tools = agent_service._get_tools(_user("alice", []))
    assert "t_ping_tool" not in {t["name"] for t in tools}


def test_execute_tool_dispatches_to_module(fake_module, brain):
    fake_module("t_agent_tools", _MANIFEST_SRC, agent_tools_src=_AGENT_TOOLS_SRC)
    mod_store_service.mark_installed("t_agent_tools", by="tester")

    result = agent_service._execute_tool("t_ping_tool", {}, _user("alice", []))
    assert result == {"pong": True, "for_user": "alice"}


def test_execute_tool_unknown_name_still_returns_error(brain):
    result = agent_service._execute_tool("definitely_not_a_real_tool", {}, _user("alice", []))
    assert "error" in result
    assert "Unknown tool" in result["error"]
