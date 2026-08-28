"""Tests for approve mode — writes pause for user approval, reads run freely."""

import json
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

    async def fake(system, messages, tools, **kwargs):
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


def test_new_tools_are_write_gated_by_default(admin):
    """Every tool not explicitly allowlisted as read-only must pause in approve mode.

    Uses the real _get_tools()/read_only_agent_tool_names() combination
    (not just the static core _USER_TOOLS/_ADMIN_TOOLS lists) so this covers
    module-contributed tools too — add_task/delete_task moved into
    module_packages/tasks/backend/agent_tools.py when Tasks converted
    (2026-08-25), same as every other module's own tools already needed
    this same live-gating check, not a special case for tasks. household
    and assets are NOT locked (unlike tasks), so they need an explicit
    mark_installed here for add_shared_task's/create_asset's schemas to
    appear in _get_tools() at all — also exercises admin_agent_tools' own
    gate for real, since the `admin` fixture really is an admin."""
    from module_registry import read_only_agent_tool_names
    from services import mod_store_service

    mod_store_service.mark_installed("household", by="tester")
    mod_store_service.mark_installed("assets", by="tester")
    all_names = {t["name"] for t in agent_service._get_tools(admin)}
    read_names = agent_service._READ_TOOLS | read_only_agent_tool_names()
    write_names = all_names - read_names - {"propose_plan"}
    # Spot-check known writes are gated
    for name in (
        "add_task",
        "delete_task",
        "write_brain_file",
        "add_shared_task",
        "update_profile",
        "create_asset",
        "update_asset",
        "archive_asset",
        "delete_asset",
        "create_asset_template",
    ):
        assert name in write_names
    # And known reads are not
    for name in (
        "list_tasks",
        "search_brain",
        "get_profile",
        "list_household_members",
        "list_assets",
        "list_asset_templates",
    ):
        assert name not in write_names


# ---------------------------------------------------------------------------
# Generic pause/resume mechanism (2026-08-09) — the approve-mode replay fix.
# Before this, Approve re-sent free text ("Yes, go ahead.") and the model
# re-derived what to do from its own prior turn; these tests prove the
# persisted call is *replayed*, not re-derived.
# ---------------------------------------------------------------------------


def test_pending_turn_store_roundtrip_and_delete(admin):
    pending = {
        "run_id": "test-run-1",
        "kind": "write",
        "mode": "approve",
        "goal": "add a task",
        "messages": [],
        "pending_tool_calls": [{"id": "t1", "name": "add_task", "input": {"title": "X"}}],
        "steps": [],
        "workspace": "personal",
        "cross_workspace": False,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    agent_service.save_pending_turn(admin["name"], pending)
    loaded = agent_service.load_pending_turn(admin["name"], "test-run-1")
    assert loaded is not None
    assert loaded["pending_tool_calls"][0]["input"]["title"] == "X"

    agent_service.delete_pending_turn(admin["name"], "test-run-1")
    assert agent_service.load_pending_turn(admin["name"], "test-run-1") is None


@pytest.mark.asyncio
async def test_approve_pause_persists_replayable_pending_turn(admin, monkeypatch):
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

    pending = agent_service.load_pending_turn(admin["name"], run["id"])
    assert pending is not None
    assert pending["kind"] == "write"
    assert pending["pending_tool_calls"] == [
        {"id": "t1", "name": "add_task", "input": {"title": "Buy milk", "category": "Home"}}
    ]
    # The assistant's tool-use turn must be in the frozen messages snapshot —
    # this is what the original bug never appended, making replay impossible.
    assert pending["messages"][-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_resume_replays_exact_original_action_not_a_reguess(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion(
            [_tool_response("add_task", {"title": "Buy milk", "category": "Home"}, "Adding milk.")]
        ),
    )
    run = await agent_service.run_agent(admin, "add a task to buy milk", [], "sys", mode="approve")
    pending = agent_service.load_pending_turn(admin["name"], run["id"])

    # If the model were asked again (the old, buggy behavior), it would now react
    # to a completely different queued response — proving a bug would show up as
    # the WRONG task getting created.
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion([_text_response("Done — added Buy bread.")]),
    )
    resumed = await agent_service.run_agent(
        admin, "", [], "sys", mode="approve", resume={**pending, "decision": "approve"}
    )

    assert resumed["status"] == "agent"
    tasks = task_service.list_tasks(admin["name"])
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Buy milk"  # the ORIGINAL proposal, never "Buy bread"


@pytest.mark.asyncio
async def test_resume_decline_produces_structured_result_not_free_text(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion([_tool_response("add_task", {"title": "Buy milk", "category": "Home"})]),
    )
    run = await agent_service.run_agent(admin, "add a task to buy milk", [], "sys", mode="approve")
    pending = agent_service.load_pending_turn(admin["name"], run["id"])

    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion([_text_response("Okay, I won't make that change.")]),
    )
    resumed = await agent_service.run_agent(
        admin, "", [], "sys", mode="approve", resume={**pending, "decision": "decline"}
    )

    assert task_service.list_tasks(admin["name"]) == []
    tool_step = next(s for s in resumed["steps"] if s["type"] == "tool_call")
    assert tool_step["output"] == {"declined": True}


@pytest.mark.asyncio
async def test_resume_completion_drops_the_resolved_pending_step(admin, monkeypatch):
    """Bug found live in production, 2026-08-10: a resolved pending_write left
    over in `steps` made a genuinely-completed run look like it was still
    awaiting approval — the frontend rendered a phantom ApprovalCard with no
    real run_id behind it (a completed response never carries one), and
    clicking it 422'd with "field required" on the missing run_id."""
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion([_tool_response("add_task", {"title": "Buy milk", "category": "Home"})]),
    )
    run = await agent_service.run_agent(admin, "add a task to buy milk", [], "sys", mode="approve")
    pending = agent_service.load_pending_turn(admin["name"], run["id"])

    # The model has nothing further to do once the write actually lands.
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion([_text_response("Done — added Buy milk.")]),
    )
    resumed = await agent_service.run_agent(
        admin, "", [], "sys", mode="approve", resume={**pending, "decision": "approve"}
    )

    assert resumed["status"] == "agent"  # not "awaiting_approval"
    assert not any(s["type"] == "pending_write" for s in resumed["steps"])
    # The replay itself must still show up as a real, resolved tool_call.
    assert any(s["type"] == "tool_call" and s["tool"] == "add_task" for s in resumed["steps"])


@pytest.mark.asyncio
async def test_resume_chain_of_two_writes_leaves_no_stale_pending_step(admin, monkeypatch):
    """A genuine second write (not a stale leftover) still pauses correctly,
    and once *that* one resolves too, nothing pending is left over either."""
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion([_tool_response("add_task", {"title": "Buy milk", "category": "Home"})]),
    )
    run = await agent_service.run_agent(admin, "add two tasks", [], "sys", mode="approve")
    pending1 = agent_service.load_pending_turn(admin["name"], run["id"])

    # Resuming write #1, the model immediately asks to do a second write.
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion([_tool_response("add_task", {"title": "Buy bread", "category": "Home"})]),
    )
    resumed1 = await agent_service.run_agent(
        admin, "", [], "sys", mode="approve", resume={**pending1, "decision": "approve"}
    )
    assert resumed1["status"] == "awaiting_approval"  # a REAL second pause
    assert resumed1["id"] == run["id"]  # same run_id carried through the chain

    pending2 = agent_service.load_pending_turn(admin["name"], resumed1["id"])
    assert pending2["pending_tool_calls"][0]["input"]["title"] == "Buy bread"
    # The first (already-resolved) pending_write must not have leaked forward.
    assert not any(s["type"] == "pending_write" for s in resumed1["steps"][:-1])

    monkeypatch.setattr(
        agent_service, "agent_completion", _fake_completion([_text_response("Done!")])
    )
    resumed2 = await agent_service.run_agent(
        admin, "", [], "sys", mode="approve", resume={**pending2, "decision": "approve"}
    )

    assert resumed2["status"] == "agent"
    assert not any(s["type"] == "pending_write" for s in resumed2["steps"])
    tasks = task_service.list_tasks(admin["name"])
    assert {t["title"] for t in tasks} == {"Buy milk", "Buy bread"}


# ---------------------------------------------------------------------------
# ask_user_question (2026-08-09) — built on the same pause/resume mechanism.
# ---------------------------------------------------------------------------

_CATEGORY_QUESTION = {
    "question": "Which category should this go under?",
    "header": "Category",
    "options": [
        {"label": "Home", "description": "Household chores and errands"},
        {"label": "Work", "description": "Job-related tasks"},
    ],
    "multi_select": False,
}


@pytest.mark.asyncio
async def test_ask_user_question_pauses_and_executes_nothing(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion(
            [
                _tool_response(
                    "ask_user_question", _CATEGORY_QUESTION, "Let me check something first."
                )
            ]
        ),
    )
    run = await agent_service.run_agent(admin, "add a task", [], "sys", mode="approve")

    assert run["status"] == "awaiting_answer"
    q = next(s for s in run["steps"] if s["type"] == "pending_question")
    assert q["question"] == _CATEGORY_QUESTION["question"]
    assert len(q["options"]) == 2
    assert task_service.list_tasks(admin["name"]) == []


@pytest.mark.asyncio
async def test_ask_user_question_pauses_even_in_auto_mode(admin, monkeypatch):
    """Auto mode otherwise executes writes freely, but a question isn't a write
    and always needs a real human answer, regardless of granted autonomy."""
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion([_tool_response("ask_user_question", _CATEGORY_QUESTION)]),
    )
    run = await agent_service.run_agent(admin, "set up a reminder", [], "sys", mode="auto")
    assert run["status"] == "awaiting_answer"


@pytest.mark.asyncio
async def test_resume_answer_reaches_model_as_exact_tool_result(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion([_tool_response("ask_user_question", _CATEGORY_QUESTION)]),
    )
    run = await agent_service.run_agent(admin, "add a task", [], "sys", mode="approve")
    pending = agent_service.load_pending_turn(admin["name"], run["id"])
    assert pending["kind"] == "question"

    captured = {}

    async def fake_reaction(system, messages, tools, **kwargs):
        last_user_msg = messages[-1]
        captured["tool_result_content"] = last_user_msg["content"][0]["content"]
        return _text_response("Got it — Home it is.")

    monkeypatch.setattr(agent_service, "agent_completion", fake_reaction)

    resumed = await agent_service.run_agent(
        admin, "", [], "sys", mode="approve", resume={**pending, "answer": ["Home"]}
    )

    assert resumed["status"] == "agent"
    assert json.loads(captured["tool_result_content"]) == {"answer": ["Home"]}


# ---------------------------------------------------------------------------
# propose_plan migrated onto the pause/resume mechanism (2026-08-09) — used to
# be a bare echo relying entirely on the system prompt to make the model wait.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_plan_pauses_and_persists_pending_turn(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion(
            [
                _tool_response(
                    "propose_plan",
                    {
                        "summary": "Create 3 tasks for your week",
                        "actions": ["Task A", "Task B", "Task C"],
                    },
                    "Here's my plan.",
                )
            ]
        ),
    )
    run = await agent_service.run_agent(admin, "plan my week", [], "sys", mode="plan")

    assert run["status"] == "awaiting_approval"
    p = next(s for s in run["steps"] if s["type"] == "pending_plan")
    assert p["summary"] == "Create 3 tasks for your week"
    assert p["actions"] == ["Task A", "Task B", "Task C"]

    pending = agent_service.load_pending_turn(admin["name"], run["id"])
    assert pending["kind"] == "plan"
    assert pending["pending_tool_calls"][0]["name"] == "propose_plan"


@pytest.mark.asyncio
async def test_propose_plan_resume_approve_continues_from_persisted_plan(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion(
            [
                _tool_response(
                    "propose_plan", {"summary": "Add a task", "actions": ["Add: Buy milk"]}
                )
            ]
        ),
    )
    run = await agent_service.run_agent(admin, "plan my week", [], "sys", mode="plan")
    pending = agent_service.load_pending_turn(admin["name"], run["id"])

    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion(
            [
                _tool_response("add_task", {"title": "Buy milk", "category": "Home"}),
                _text_response("Done!"),
            ]
        ),
    )
    resumed = await agent_service.run_agent(
        admin, "", [], "sys", mode="plan", resume={**pending, "decision": "approve"}
    )

    assert resumed["status"] == "agent"
    tasks = task_service.list_tasks(admin["name"])
    assert len(tasks) == 1 and tasks[0]["title"] == "Buy milk"


@pytest.mark.asyncio
async def test_propose_plan_resume_decline_produces_structured_result(admin, monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "agent_completion",
        _fake_completion(
            [_tool_response("propose_plan", {"summary": "Add a task", "actions": ["x"]})]
        ),
    )
    run = await agent_service.run_agent(admin, "plan my week", [], "sys", mode="plan")
    pending = agent_service.load_pending_turn(admin["name"], run["id"])

    monkeypatch.setattr(
        agent_service, "agent_completion", _fake_completion([_text_response("Okay, revising.")])
    )
    resumed = await agent_service.run_agent(
        admin, "", [], "sys", mode="plan", resume={**pending, "decision": "decline"}
    )

    tool_step = next(s for s in resumed["steps"] if s["type"] == "tool_call")
    assert tool_step["output"] == {"declined": True}
    assert task_service.list_tasks(admin["name"]) == []
