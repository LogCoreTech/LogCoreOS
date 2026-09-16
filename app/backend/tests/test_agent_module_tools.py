"""Enforcement-gap + integration tests for the AI agent's module-tool
plumbing: _get_tools() must hard-exclude a disabled module's tools (the model
can never even be offered a call that's guaranteed to fail), and
_execute_tool() must actually dispatch a real tool call through to an active
module's own agent_tools.py."""

import pytest

from services import agent_service, mod_store_service
from services.ai_provider import AgentResponse, ToolCall

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


def test_module_owning_tool_finds_owning_manifests_display_name(fake_module, brain):
    fake_module("t_agent_tools", _MANIFEST_SRC, agent_tools_src=_AGENT_TOOLS_SRC)
    mod_store_service.mark_installed("t_agent_tools", by="tester")
    assert agent_service._module_owning_tool("t_ping_tool") == "Test"


def test_module_owning_tool_returns_none_for_a_core_tool(brain):
    # A core _USER_TOOLS entry, never a module's owned_agent_tools — unlike
    # add_task/delete_task, which moved into module_packages/tasks/ when
    # Tasks converted (2026-08-25) and so ARE module-owned.
    assert agent_service._module_owning_tool("list_brain_files") is None


# ---------------------------------------------------------------------------
# S12 fix (2026-09-08): the resume/replay path must re-check disabled_modules
# against the user's CURRENT tool list before executing a pending write —
# not just trust the pending_tool_calls snapshot frozen when the write was
# first proposed. Without this, a write proposed while a module was enabled,
# left unactioned, then approved after an admin disables that module for the
# user, would still execute.
# ---------------------------------------------------------------------------


def _tool_response(name: str, inputs: dict, text: str = "") -> AgentResponse:
    raw = ([{"type": "text", "text": text}] if text else []) + [
        {"type": "tool_use", "id": "t1", "name": name, "input": inputs}
    ]
    return AgentResponse(
        stop_reason="tool_use",
        text=text,
        tool_calls=[ToolCall(id="t1", name=name, input=inputs)],
        raw_content=raw,
    )


def _text_response(text: str) -> AgentResponse:
    return AgentResponse(
        stop_reason="end_turn",
        text=text,
        tool_calls=[],
        raw_content=[{"type": "text", "text": text}],
    )


def _fake_completion(responses: list[AgentResponse]):
    calls = {"n": 0}

    async def fake(system, messages, tools, **kwargs):
        resp = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        return resp

    return fake


@pytest.mark.asyncio
async def test_resume_skips_pending_write_whose_module_was_disabled_after_proposal(
    fake_module, brain, monkeypatch
):
    fake_module("t_agent_tools", _MANIFEST_SRC, agent_tools_src=_AGENT_TOOLS_SRC)
    mod_store_service.mark_installed("t_agent_tools", by="tester")
    user = _user("alice", [])

    monkeypatch.setattr(
        agent_service, "agent_completion", _fake_completion([_tool_response("t_ping_tool", {})])
    )
    run = await agent_service.run_agent(user, "ping the test tool", [], "sys", mode="approve")
    assert run["status"] == "awaiting_approval"
    pending = agent_service.load_pending_turn(user["name"], run["id"])
    assert pending["pending_tool_calls"][0]["name"] == "t_ping_tool"

    # The module is disabled for this user AFTER the write was proposed but
    # BEFORE it's approved — exactly the gap S12 closes. A freshly queued
    # completion here would prove a regression immediately: if the stale
    # write executed anyway (calling the module's real execute(), which
    # returns {"pong": ...}), the model would never even see this text.
    monkeypatch.setattr(
        agent_service, "agent_completion", _fake_completion([_text_response("Understood.")])
    )
    user_now_disabled = _user("alice", ["t_agent_tools"])
    resumed = await agent_service.run_agent(
        user_now_disabled,
        "",
        [],
        "sys",
        mode="approve",
        resume={**pending, "decision": "approve"},
    )

    tool_step = next(s for s in resumed["steps"] if s["type"] == "tool_call")
    assert tool_step["tool"] == "t_ping_tool"
    assert "error" in tool_step["output"]
    assert "no longer be completed" in tool_step["output"]["error"]
    assert "Test module was disabled" in tool_step["output"]["error"]


@pytest.mark.asyncio
async def test_resume_still_executes_pending_write_when_module_remains_enabled(
    fake_module, brain, monkeypatch
):
    """Regression guard for the fix above: a module that's still enabled at
    resume time must keep executing normally, exactly as before."""
    fake_module("t_agent_tools", _MANIFEST_SRC, agent_tools_src=_AGENT_TOOLS_SRC)
    mod_store_service.mark_installed("t_agent_tools", by="tester")
    user = _user("bob", [])

    monkeypatch.setattr(
        agent_service, "agent_completion", _fake_completion([_tool_response("t_ping_tool", {})])
    )
    run = await agent_service.run_agent(user, "ping the test tool", [], "sys", mode="approve")
    pending = agent_service.load_pending_turn(user["name"], run["id"])

    monkeypatch.setattr(
        agent_service, "agent_completion", _fake_completion([_text_response("Done.")])
    )
    resumed = await agent_service.run_agent(
        user, "", [], "sys", mode="approve", resume={**pending, "decision": "approve"}
    )

    tool_step = next(s for s in resumed["steps"] if s["type"] == "tool_call")
    assert tool_step["output"] == {"pong": True, "for_user": "bob"}
