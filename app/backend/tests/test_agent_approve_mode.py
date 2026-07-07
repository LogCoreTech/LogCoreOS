"""Tests for approve mode — writes pause for user approval, reads run freely."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import agent_service, auth_service, task_service
from services.ai_provider import AgentResponse, ToolCall


@pytest.fixture()
def admin(brain):
    user = auth_service.create_user("admin@example.com", "password123", "Alice", role="admin")
    yield user
    auth_service._revoked_jtis.clear()


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
    """Return an async agent_completion stub that yields the given responses in order."""
    calls = {"n": 0}

    async def fake(system, messages, tools):
        resp = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        return resp

    return fake


@pytest.mark.asyncio
async def test_approve_mode_pauses_write(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion(
            [
                _tool_response(
                    "add_task", {"title": "Buy milk", "category": "Home"}, "Adding that now."
                )
            ]
        ),
    )
    run = await agent_service.run_agent(admin, "add a task to buy milk", [], "sys", mode="approve")

    assert run["status"] == "awaiting_approval"
    pending = [s for s in run["steps"] if s["type"] == "pending_write"]
    assert len(pending) == 1
    assert pending[0]["tool"] == "add_task"
    assert pending[0]["input"]["title"] == "Buy milk"
    # Nothing was written
    assert task_service.list_tasks(admin["name"]) == []


@pytest.mark.asyncio
async def test_approve_mode_pause_uses_leadin_text(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion([_tool_response("add_task", {"title": "X", "category": "Home"})]),
    )
    run = await agent_service.run_agent(admin, "add x", [], "sys", mode="approve")
    assert run["final_answer"] == "I need your approval to make these changes."


@pytest.mark.asyncio
async def test_approve_mode_executes_reads(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion(
            [
                _tool_response("list_tasks", {}),
                _text_response("You have no tasks."),
            ]
        ),
    )
    run = await agent_service.run_agent(admin, "what are my tasks?", [], "sys", mode="approve")

    assert run["status"] == "agent"
    assert run["final_answer"] == "You have no tasks."
    tool_steps = [s for s in run["steps"] if s["type"] == "tool_call"]
    assert len(tool_steps) == 1 and tool_steps[0]["tool"] == "list_tasks"


@pytest.mark.asyncio
async def test_auto_mode_still_executes_writes(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion(
            [
                _tool_response("add_task", {"title": "Buy milk", "category": "Home"}),
                _text_response("Done — added Buy milk."),
            ]
        ),
    )
    run = await agent_service.run_agent(admin, "add a task to buy milk", [], "sys", mode="auto")

    assert run["status"] == "agent"
    tasks = task_service.list_tasks(admin["name"])
    assert len(tasks) == 1 and tasks[0]["title"] == "Buy milk"


def test_new_tools_are_write_gated_by_default():
    """Every tool not explicitly allowlisted as read-only must pause in approve mode."""
    all_names = {t["name"] for t in agent_service._USER_TOOLS} | {
        t["name"] for t in agent_service._ADMIN_TOOLS
    }
    write_names = all_names - agent_service._READ_TOOLS - {"propose_plan"}
    # Spot-check known writes are gated
    for name in (
        "add_task",
        "delete_task",
        "write_brain_file",
        "add_shared_task",
        "update_profile",
    ):
        assert name in write_names
    # And known reads are not
    for name in ("list_tasks", "search_brain", "get_profile", "list_household_members"):
        assert name not in write_names
