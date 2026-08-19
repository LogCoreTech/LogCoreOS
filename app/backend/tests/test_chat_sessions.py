"""Tests for chat_sessions.json (background execution + multi-conversation
UI, 2026-08-15): agent_service's session-index helpers, routers.chat's
archive-writing helper, and the main /chat handler's session bookkeeping
end-to-end (called directly, same pattern test_workspace_entitlement.py uses
for router-level functions, combined with test_agent_approve_mode.py's
agent_completion mocking)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from config import settings
from routers.chat import ChatRequest, ResumeAction, _write_chat_archive, chat, get_pending
from services import agent_service, auth_service
from services.ai_provider import AgentResponse, ToolCall
from services.file_service import read_markdown, ws_path


@pytest.fixture()
def alice(brain):
    user = auth_service.create_user("alice@example.com", "password123", "Alice")
    yield user
    auth_service._revoked_jtis.clear()


# ---------------------------------------------------------------------------
# agent_service session-index helpers
# ---------------------------------------------------------------------------


def test_upsert_session_creates_then_updates(brain):
    entry = agent_service.upsert_session(
        "Alice", "personal", "c1", filename="a.md", title="Hi", status="running"
    )
    assert entry["chat_id"] == "c1"
    assert agent_service.get_session("Alice", "personal", "c1")["status"] == "running"

    agent_service.upsert_session("Alice", "personal", "c1", status="idle")
    updated = agent_service.get_session("Alice", "personal", "c1")
    assert updated["status"] == "idle"
    assert updated["filename"] == "a.md"  # untouched fields survive a partial update


def test_upsert_session_moves_touched_entry_to_front(brain):
    agent_service.upsert_session("Alice", "personal", "c1", title="First")
    agent_service.upsert_session("Alice", "personal", "c2", title="Second")
    agent_service.upsert_session("Alice", "personal", "c1", title="First", status="idle")
    ids = [s["chat_id"] for s in agent_service.load_sessions("Alice", "personal")]
    assert ids == ["c1", "c2"]


def test_sessions_are_workspace_scoped(brain):
    agent_service.upsert_session("Alice", "personal", "c1", title="Personal chat")
    agent_service.upsert_session("Alice", "business", "c2", title="Business chat")
    assert [s["chat_id"] for s in agent_service.load_sessions("Alice", "personal")] == ["c1"]
    assert [s["chat_id"] for s in agent_service.load_sessions("Alice", "business")] == ["c2"]
    assert agent_service.get_session("Alice", "business", "c1") is None


def test_mark_session_read_clears_unread_only_for_that_session(brain):
    agent_service.upsert_session("Alice", "personal", "c1", title="A", unread=True)
    agent_service.upsert_session("Alice", "personal", "c2", title="B", unread=True)
    assert agent_service.mark_session_read("Alice", "personal", "c1") is True
    sessions = {s["chat_id"]: s["unread"] for s in agent_service.load_sessions("Alice", "personal")}
    assert sessions == {"c1": False, "c2": True}


def test_mark_session_read_returns_false_for_unknown_chat_id(brain):
    assert agent_service.mark_session_read("Alice", "personal", "does-not-exist") is False


def test_delete_session_by_filename_removes_matching_entry(brain):
    agent_service.upsert_session("Alice", "personal", "c1", filename="keep.md", title="Keep")
    agent_service.upsert_session("Alice", "personal", "c2", filename="gone.md", title="Gone")
    agent_service.delete_session_by_filename("Alice", "personal", "gone.md")
    ids = [s["chat_id"] for s in agent_service.load_sessions("Alice", "personal")]
    assert ids == ["c1"]


def test_sessions_capped(brain):
    for i in range(agent_service._SESSIONS_CAP + 5):
        agent_service.upsert_session("Alice", "personal", f"c{i}", title=str(i))
    assert len(agent_service.load_sessions("Alice", "personal")) == agent_service._SESSIONS_CAP


# ---------------------------------------------------------------------------
# _write_chat_archive
# ---------------------------------------------------------------------------


def test_write_chat_archive_produces_expected_markdown(brain):
    auth_service.create_user("bob@example.com", "password123", "Bob")
    _write_chat_archive(
        "Bob",
        "personal",
        "test.md",
        "My Chat",
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello there"}],
    )
    content = read_markdown(ws_path("Bob", "personal") / "Chats" / "test.md")
    assert content.startswith("# My Chat")
    assert "**You**: hi" in content
    assert "**AI**: hello there" in content


def test_write_chat_archive_overwrites_same_filename(brain):
    auth_service.create_user("carol@example.com", "password123", "Carol")
    _write_chat_archive("Carol", "personal", "t.md", "T", [{"role": "user", "content": "one"}])
    _write_chat_archive(
        "Carol",
        "personal",
        "t.md",
        "T",
        [{"role": "user", "content": "one"}, {"role": "assistant", "content": "two"}],
    )
    content = read_markdown(ws_path("Carol", "personal") / "Chats" / "t.md")
    assert content.count("**You**: one") == 1
    assert "**AI**: two" in content


# ---------------------------------------------------------------------------
# POST /chat handler — session bookkeeping end-to-end (agent_completion
# mocked, same pattern as test_agent_approve_mode.py)
# ---------------------------------------------------------------------------


def _text_response(text: str) -> AgentResponse:
    return AgentResponse(
        stop_reason="end_turn",
        text=text,
        tool_calls=[],
        raw_content=[{"type": "text", "text": text}],
    )


def _fake_completion(text: str):
    async def fake(system, messages, tools, **kwargs):
        return _text_response(text)

    return fake


@pytest.mark.asyncio
async def test_chat_creates_a_session_on_first_message(alice, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")
    monkeypatch.setattr(agent_service, "agent_completion", _fake_completion("Hello yourself!"))

    req = ChatRequest(chat_id="chat-1", message="hi there", mode="auto")
    result = await chat(req, current_user=alice, workspace="personal")

    assert result["response"] == "Hello yourself!"
    assert result["chat_id"] == "chat-1"

    session = agent_service.get_session("Alice", "personal", "chat-1")
    assert session is not None
    assert session["status"] == "idle"
    assert session["title"] == "hi there"
    assert session["unread"] is True
    assert session["last_message_preview"] == "Hello yourself!"

    content = read_markdown(ws_path("Alice", "personal") / "Chats" / session["filename"])
    assert "**You**: hi there" in content
    assert "**AI**: Hello yourself!" in content


@pytest.mark.asyncio
async def test_chat_second_message_reuses_same_archive_file(alice, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")
    monkeypatch.setattr(agent_service, "agent_completion", _fake_completion("First reply"))
    req1 = ChatRequest(chat_id="chat-2", message="first", mode="auto")
    await chat(req1, current_user=alice, workspace="personal")
    filename_after_first = agent_service.get_session("Alice", "personal", "chat-2")["filename"]

    monkeypatch.setattr(agent_service, "agent_completion", _fake_completion("Second reply"))
    req2 = ChatRequest(
        chat_id="chat-2",
        message="second",
        mode="auto",
        history=[
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "First reply"},
        ],
    )
    await chat(req2, current_user=alice, workspace="personal")
    session = agent_service.get_session("Alice", "personal", "chat-2")

    assert session["filename"] == filename_after_first  # same file, not a new one
    content = read_markdown(ws_path("Alice", "personal") / "Chats" / session["filename"])
    assert "**You**: first" in content
    assert "**You**: second" in content
    assert "**AI**: Second reply" in content


@pytest.mark.asyncio
async def test_chat_resets_session_status_if_agent_raises(alice, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")

    async def boom(*a, **kw):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(agent_service, "agent_completion", boom)

    req = ChatRequest(chat_id="chat-3", message="hi", mode="auto")
    with pytest.raises(RuntimeError):
        await chat(req, current_user=alice, workspace="personal")

    session = agent_service.get_session("Alice", "personal", "chat-3")
    assert session["status"] == "idle"  # never stuck showing "running"


@pytest.mark.asyncio
async def test_chat_saves_the_user_message_even_if_the_agent_call_raises(alice, monkeypatch):
    # Regression coverage (owner report, 2026-08-17): the user's own message
    # used to only ever get archived as part of the single end-of-turn write
    # alongside the assistant's reply — if the agent call raised (or the
    # connection dropped) before that point, the message the user typed was
    # never saved anywhere, not even the fact they sent it. Confirms the
    # split-write fix: the user's message is saved BEFORE the agent call.
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")

    async def boom(*a, **kw):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(agent_service, "agent_completion", boom)

    req = ChatRequest(chat_id="chat-4", message="please remember this", mode="auto")
    with pytest.raises(RuntimeError):
        await chat(req, current_user=alice, workspace="personal")

    session = agent_service.get_session("Alice", "personal", "chat-4")
    content = read_markdown(ws_path("Alice", "personal") / "Chats" / session["filename"])
    assert "**You**: please remember this" in content


# ---------------------------------------------------------------------------
# GET /chat/pending/{chat_id} (2026-08-15) — re-attaching a live pending-turn
# card onto a reopened session. Regression coverage for a real bug: reopening
# a saved chat left mid-approval reloaded the plain "I need your approval..."
# text fine (it's in the .md archive) but had no way to actually act on it,
# since the archive itself never stored the interactive card's steps/run_id.
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


@pytest.mark.asyncio
async def test_get_pending_returns_the_live_card_for_a_paused_write(alice, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")

    async def fake(system, messages, tools, **kwargs):
        return _tool_response("add_task", {"title": "Buy milk"}, "Adding that now.")

    monkeypatch.setattr(agent_service, "agent_completion", fake)

    req = ChatRequest(chat_id="chat-pending-1", message="add a task", mode="approve")
    result = await chat(req, current_user=alice, workspace="personal")
    assert result["mode"] == "awaiting_approval"
    run_id = result["run_id"]

    session = agent_service.get_session("Alice", "personal", "chat-pending-1")
    assert session["status"] == "awaiting_approval"

    pending = get_pending("chat-pending-1", current_user=alice)
    assert pending is not None
    assert pending["run_id"] == run_id
    assert pending["mode"] == "awaiting_approval"
    types = [s["type"] for s in pending["steps"]]
    assert "pending_write" in types


@pytest.mark.asyncio
async def test_get_pending_derives_awaiting_answer_for_a_question(alice, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")

    async def fake(system, messages, tools, **kwargs):
        raw = [
            {
                "type": "tool_use",
                "id": "t1",
                "name": "ask_user_question",
                "input": {
                    "question": "Which one?",
                    "header": "Pick",
                    "options": [],
                    "multi_select": False,
                },
            }
        ]
        return AgentResponse(
            stop_reason="tool_use",
            text="",
            tool_calls=[
                ToolCall(
                    id="t1",
                    name="ask_user_question",
                    input={
                        "question": "Which one?",
                        "header": "Pick",
                        "options": [],
                        "multi_select": False,
                    },
                )
            ],
            raw_content=raw,
        )

    monkeypatch.setattr(agent_service, "agent_completion", fake)

    req = ChatRequest(chat_id="chat-pending-2", message="do the thing", mode="auto")
    result = await chat(req, current_user=alice, workspace="personal")
    assert result["mode"] == "awaiting_answer"

    pending = get_pending("chat-pending-2", current_user=alice)
    assert pending["mode"] == "awaiting_answer"
    assert any(s["type"] == "pending_question" for s in pending["steps"])


@pytest.mark.asyncio
async def test_get_pending_returns_none_once_resolved(alice, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")

    async def fake(system, messages, tools, **kwargs):
        return _tool_response("add_task", {"title": "Buy milk"}, "Adding that now.")

    monkeypatch.setattr(agent_service, "agent_completion", fake)
    req = ChatRequest(chat_id="chat-pending-3", message="add a task", mode="approve")
    result = await chat(req, current_user=alice, workspace="personal")
    run_id = result["run_id"]

    async def fake_followup(system, messages, tools, **kwargs):
        return _text_response("Done!")

    monkeypatch.setattr(agent_service, "agent_completion", fake_followup)
    resume_req = ChatRequest(
        chat_id="chat-pending-3",
        resume=ResumeAction(run_id=run_id, decision="approve"),
    )
    await chat(resume_req, current_user=alice, workspace="personal")

    assert get_pending("chat-pending-3", current_user=alice) is None


def test_get_pending_returns_none_for_unknown_chat_id(alice):
    assert get_pending("no-such-chat", current_user=alice) is None


# ---------------------------------------------------------------------------
# Resume history shape (2026-08-15) — regression for a real reported bug:
# "chat breaks after accepting an approval card, any message after that
# returns unexpected role 'assistant'". Chat.jsx's sendResume() used to send
# the SAME trimmed history shape a plain send() does (ending in an assistant
# turn), which silently dropped the actual triggering user message — that
# message is legitimately the LAST entry when a turn is paused, since a
# normal alternating conversation always has a user turn directly before the
# assistant turn that's now pending. The server then archived
# `history + [resumed_reply]` with that user turn missing, leaving two
# assistant entries adjacent in the .md file; reloading that archive later
# loaded the broken pair straight into live state, and the next real send
# 422'd. Fixed on both ends: Chat.jsx's new toResumeHistory() correctly sends
# a history ending in the triggering user message, and ChatRequest's
# validator now accepts that shape specifically for a resume (a plain send's
# history must still end in assistant).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_history_ending_in_user_is_accepted(alice, monkeypatch):
    """The exact shape Chat.jsx's new toResumeHistory() sends — must not 422."""
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")

    async def fake(system, messages, tools, **kwargs):
        return _tool_response("add_task", {"title": "Buy milk"}, "Adding that now.")

    monkeypatch.setattr(agent_service, "agent_completion", fake)
    req = ChatRequest(chat_id="chat-resume-1", message="add a task", mode="approve")
    result = await chat(req, current_user=alice, workspace="personal")
    run_id = result["run_id"]

    async def fake_followup(system, messages, tools, **kwargs):
        return _text_response("Done!")

    monkeypatch.setattr(agent_service, "agent_completion", fake_followup)
    # A history ending in "user" — toResumeHistory()'s shape, previously
    # rejected by the old "must end with an assistant message" check.
    resume_req = ChatRequest(
        chat_id="chat-resume-1",
        history=[{"role": "user", "content": "add a task"}],
        resume=ResumeAction(run_id=run_id, decision="approve"),
    )
    resume_result = await chat(resume_req, current_user=alice, workspace="personal")
    assert resume_result["response"] == "Done!"


@pytest.mark.asyncio
async def test_resume_then_followup_send_does_not_break_history_alternation(alice, monkeypatch):
    """End-to-end regression: send -> pending approval -> resume (real
    Chat.jsx history shape) -> reload the archive (same as a page remount) ->
    a plain follow-up send must succeed, not 422 with "unexpected role
    'assistant'"."""
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")

    async def fake(system, messages, tools, **kwargs):
        return _tool_response("add_task", {"title": "Buy milk"}, "Adding that now.")

    monkeypatch.setattr(agent_service, "agent_completion", fake)
    req = ChatRequest(chat_id="chat-resume-2", message="add a task", mode="approve")
    result = await chat(req, current_user=alice, workspace="personal")
    run_id = result["run_id"]

    async def fake_followup(system, messages, tools, **kwargs):
        return _text_response("Done!")

    monkeypatch.setattr(agent_service, "agent_completion", fake_followup)
    resume_req = ChatRequest(
        chat_id="chat-resume-2",
        history=[{"role": "user", "content": "add a task"}],
        resume=ResumeAction(run_id=run_id, decision="approve"),
    )
    await chat(resume_req, current_user=alice, workspace="personal")

    # The archive must alternate correctly — no two adjacent assistant turns.
    session = agent_service.get_session("Alice", "personal", "chat-resume-2")
    content = read_markdown(ws_path("Alice", "personal") / "Chats" / session["filename"])
    lines = [l for l in content.split("\n") if l.startswith("**You**:") or l.startswith("**AI**:")]
    assert lines == ["**You**: add a task", "**AI**: Done!"]

    # Simulate reloading that archive into a fresh client (a page remount) —
    # this is exactly the history Chat.jsx would compute from the reloaded
    # messages — then a plain follow-up send must not 422.
    async def fake_second(system, messages, tools, **kwargs):
        return _text_response("Second reply")

    monkeypatch.setattr(agent_service, "agent_completion", fake_second)
    followup_req = ChatRequest(
        chat_id="chat-resume-2",
        message="another message",
        mode="approve",
        history=[
            {"role": "user", "content": "add a task"},
            {"role": "assistant", "content": "Done!"},
        ],
    )
    followup_result = await chat(followup_req, current_user=alice, workspace="personal")
    assert followup_result["response"] == "Second reply"


# ---------------------------------------------------------------------------
# Chat presence (2026-08-15) — owner ask: only notify when the user isn't
# already looking at the conversation.
# ---------------------------------------------------------------------------


def test_is_chat_present_true_right_after_recording(brain):
    auth_service.create_user("dana@example.com", "password123", "Dana")
    assert agent_service.is_chat_present("Dana", "chat-x") is False
    agent_service.record_chat_presence("Dana", "chat-x")
    assert agent_service.is_chat_present("Dana", "chat-x") is True


def test_is_chat_present_false_for_a_different_chat_id(brain):
    auth_service.create_user("dana@example.com", "password123", "Dana")
    agent_service.record_chat_presence("Dana", "chat-x")
    assert agent_service.is_chat_present("Dana", "chat-y") is False


def test_is_chat_present_false_once_stale(brain):
    from datetime import datetime, timedelta, timezone

    from services.file_service import write_json

    auth_service.create_user("dana@example.com", "password123", "Dana")
    stale_seen_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=agent_service._PRESENCE_STALE_AFTER_SECONDS + 5)
    ).isoformat()
    write_json(
        agent_service._presence_path("Dana"), {"chat_id": "chat-x", "seen_at": stale_seen_at}
    )
    assert agent_service.is_chat_present("Dana", "chat-x") is False


@pytest.mark.asyncio
async def test_chat_skips_notification_when_user_present(alice, monkeypatch):
    """When Chat.jsx has pinged presence for this exact chat_id, the
    completion notification is skipped and the session isn't marked unread —
    the user is already watching it complete live."""
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")
    monkeypatch.setattr(agent_service, "agent_completion", _fake_completion("Hi!"))

    notified = []
    monkeypatch.setattr(
        "services.suggestions_service.notify_user",
        lambda *a, **kw: notified.append((a, kw)),
    )

    agent_service.record_chat_presence("Alice", "chat-present-1")
    req = ChatRequest(chat_id="chat-present-1", message="hi", mode="auto")
    await chat(req, current_user=alice, workspace="personal")

    assert notified == []
    session = agent_service.get_session("Alice", "personal", "chat-present-1")
    assert session["unread"] is False


@pytest.mark.asyncio
async def test_chat_sends_notification_when_user_not_present(alice, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-tests")
    monkeypatch.setattr(agent_service, "agent_completion", _fake_completion("Hi!"))

    notified = []
    monkeypatch.setattr(
        "services.suggestions_service.notify_user",
        lambda *a, **kw: notified.append((a, kw)),
    )

    # No presence recorded for this chat_id.
    req = ChatRequest(chat_id="chat-present-2", message="hi", mode="auto")
    await chat(req, current_user=alice, workspace="personal")

    assert len(notified) == 1
    session = agent_service.get_session("Alice", "personal", "chat-present-2")
    assert session["unread"] is True
