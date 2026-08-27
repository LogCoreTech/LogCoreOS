"""Tests for agent_service.py's own chat_sessions.json + presence
infrastructure — pure agent_service calls, unaffected by chat/'s own
2026-08-26 conversion since none of this is router-specific (routers/
chat.py moved into module_packages/chat/backend/router.py; its own
_write_chat_archive/POST-handler/pending-turn tests moved with it into
module_packages/chat/tests/test_chat_router.py — see that file for the
session-bookkeeping-end-to-end and presence-notification-skip coverage
that used to live here)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import agent_service, auth_service

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
