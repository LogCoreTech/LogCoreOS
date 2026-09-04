"""Tests for routers/welcome_back.py — mirrors routers/search.py's own shape
(login-required, no module gate)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from routers.welcome_back import check
from services import presence_service


@pytest.fixture()
def alice(brain):
    from services import auth_service

    user = auth_service.create_user("alice@example.com", "password123", "Alice")
    yield user
    auth_service._revoked_jtis.clear()


@pytest.mark.asyncio
async def test_check_show_false_before_any_ping(alice):
    result = await check(alice, "personal")
    assert result == {"show": False, "summary": None}


@pytest.mark.asyncio
async def test_check_show_true_past_threshold(alice):
    from services.file_service import write_json

    stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    write_json(presence_service._presence_path("Alice"), {"seen_at": stale})

    result = await check(alice, "personal")

    assert result["show"] is True
    assert result["summary"] is None  # welcome_back_ai_summary_enabled defaults off


@pytest.mark.asyncio
async def test_check_touches_presence_so_it_does_not_immediately_refire(alice):
    from services.file_service import write_json

    stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    write_json(presence_service._presence_path("Alice"), {"seen_at": stale})

    first = await check(alice, "personal")
    assert first["show"] is True

    second = await check(alice, "personal")
    assert (
        second["show"] is False
    ), "check() must touch presence so a second call in the same visit doesn't re-fire"


@pytest.mark.asyncio
async def test_check_generates_summary_when_enabled_and_ai_configured(alice, monkeypatch):
    from services import ai_provider, task_service
    from services.file_service import write_json

    monkeypatch.setattr(ai_provider, "is_ai_configured", lambda: True)

    async def fake_chat_completion(system, messages, max_tokens=1024, *, user_name, workspace):
        return "You finished a task!"

    monkeypatch.setattr(ai_provider, "chat_completion", fake_chat_completion)

    alice["welcome_back_ai_summary_enabled"] = True
    stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    write_json(presence_service._presence_path("Alice"), {"seen_at": stale})
    task = task_service.add_task("Alice", {"title": "Water the plants", "category": "Home"})
    task_service.update_task("Alice", task["id"], {"status": "done"})

    result = await check(alice, "personal")

    assert result == {"show": True, "summary": "You finished a task!"}
