"""Tests for welcome_back_service — the middle-screen popup + optional AI
summary shown after a configurable away-threshold (item #25, 2026-09-04 UX
Polish Batch)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import presence_service
from services import welcome_back_service as svc


def _user(name="Alice", **overrides):
    return {"name": name, "role": "member", "feature_role": "member", **overrides}


# ---------------------------------------------------------------------------
# should_show
# ---------------------------------------------------------------------------


def test_should_show_false_before_any_ping(brain):
    assert svc.should_show(_user()) is False


def test_should_show_false_when_recently_seen(brain):
    presence_service.record_presence("Alice")
    assert svc.should_show(_user()) is False


def test_should_show_true_past_default_threshold(brain):
    stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    from services.file_service import write_json

    write_json(presence_service._presence_path("Alice"), {"seen_at": stale})
    assert svc.should_show(_user()) is True


def test_should_show_false_just_under_default_threshold(brain):
    recent = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
    from services.file_service import write_json

    write_json(presence_service._presence_path("Alice"), {"seen_at": recent})
    assert svc.should_show(_user()) is False


def test_should_show_respects_custom_threshold(brain):
    # 3 days away, but this user set a 2-day threshold — should show.
    three_days = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    from services.file_service import write_json

    write_json(presence_service._presence_path("Alice"), {"seen_at": three_days})
    assert svc.should_show(_user(welcome_back_threshold_days=2)) is True
    # Same 3-day gap, but a 7-day threshold — should not show.
    assert svc.should_show(_user(welcome_back_threshold_days=7)) is False


# ---------------------------------------------------------------------------
# generate_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_summary_none_when_ai_not_configured(brain, monkeypatch):
    from services import ai_provider

    monkeypatch.setattr(ai_provider, "is_ai_configured", lambda: False)
    from services.file_service import write_json

    stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    write_json(presence_service._presence_path("Alice"), {"seen_at": stale})

    assert await svc.generate_summary(_user()) is None


@pytest.mark.asyncio
async def test_generate_summary_none_when_never_seen_before(brain, monkeypatch):
    from services import ai_provider

    monkeypatch.setattr(ai_provider, "is_ai_configured", lambda: True)

    assert await svc.generate_summary(_user()) is None


@pytest.mark.asyncio
async def test_generate_summary_none_when_nothing_happened(brain, monkeypatch):
    from services import ai_provider
    from services.file_service import write_json

    monkeypatch.setattr(ai_provider, "is_ai_configured", lambda: True)
    stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    write_json(presence_service._presence_path("Alice"), {"seen_at": stale})

    # No tasks/notes/journal/events created for Alice — nothing to summarize.
    assert await svc.generate_summary(_user()) is None


@pytest.mark.asyncio
async def test_generate_summary_calls_ai_with_gathered_activity(brain, monkeypatch):
    from services import ai_provider, task_service
    from services.file_service import write_json

    monkeypatch.setattr(ai_provider, "is_ai_configured", lambda: True)

    captured = {}

    async def fake_chat_completion(system, messages, max_tokens=1024, *, user_name, workspace):
        captured["system"] = system
        captured["messages"] = messages
        return "Welcome back! You finished a task while away."

    monkeypatch.setattr(ai_provider, "chat_completion", fake_chat_completion)

    stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    write_json(presence_service._presence_path("Alice"), {"seen_at": stale})

    task = task_service.add_task("Alice", {"title": "Water the plants", "category": "Home"})
    task_service.update_task("Alice", task["id"], {"status": "done"})

    result = await svc.generate_summary(_user())

    assert result == "Welcome back! You finished a task while away."
    assert "Water the plants" in captured["messages"][0]["content"]


@pytest.mark.asyncio
async def test_generate_summary_never_reads_another_users_journal(brain, monkeypatch):
    """Journal is never shareable anywhere in this app — the summary must
    only ever read the viewer's own journal, never another user's, even
    though _gather_recent_activity has no per-module access system to lean
    on for journal specifically (it's hardcoded own-store-only)."""
    from module_packages.journal.backend import service as journal_service
    from services import ai_provider
    from services.file_service import write_json

    monkeypatch.setattr(ai_provider, "is_ai_configured", lambda: True)

    captured = {}

    async def fake_chat_completion(system, messages, max_tokens=1024, *, user_name, workspace):
        captured["messages"] = messages
        return "summary"

    monkeypatch.setattr(ai_provider, "chat_completion", fake_chat_completion)

    stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    write_json(presence_service._presence_path("Alice"), {"seen_at": stale})

    journal_service.upsert_entry("Bob", "2026-09-01", "Bob's private entry")
    journal_service.upsert_entry("Alice", "2026-09-01", "Alice's own entry")

    await svc.generate_summary(_user("Alice"))

    content = captured["messages"][0]["content"]
    assert "journal entr" in content.lower()  # Alice's own entry counted
    assert "Bob" not in content  # never leaked another user's journal content/name
