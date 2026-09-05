"""Tests for PATCH/GET /auth/me's UX Polish Batch settings fields
(2026-09-04): command_palette_enabled/actions (#3), welcome_back_ai_summary_enabled/
threshold_days (#25), tasks_filter/tasks_sort_mode (#22). No dedicated test
file for update_me()/MeUpdateRequest existed before this — a real,
pre-existing gap, not introduced by this batch."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import HTTPException

from routers.auth import MeUpdateRequest, me, update_me


@pytest.fixture()
def alice(brain):
    from services import auth_service

    user = auth_service.create_user("alice@example.com", "password123", "Alice")
    yield user
    auth_service._revoked_jtis.clear()


def test_get_me_defaults(alice):
    result = me(alice)
    assert result["command_palette_enabled"] is True
    assert result["command_palette_actions"] == []
    assert result["welcome_back_ai_summary_enabled"] is False
    assert result["welcome_back_threshold_days"] == 7
    assert result["tasks_filter"] == "pending"
    assert result["tasks_sort_mode"] == "priority"


def test_update_command_palette_settings(alice):
    update_me(
        MeUpdateRequest(command_palette_enabled=False, command_palette_actions=["tasks", "notes"]),
        alice,
        _rl=None,
    )
    from services.auth_service import get_user_by_id

    updated = get_user_by_id(alice["id"])
    result = me(updated)
    assert result["command_palette_enabled"] is False
    assert result["command_palette_actions"] == ["tasks", "notes"]


def test_command_palette_actions_must_be_list_of_strings():
    # Pydantic's own list[str] typing rejects this at construction time
    # (a real HTTP request with the wrong type never reaches update_me() at
    # all — FastAPI 422s it during request parsing) — there is deliberately
    # no redundant hand-written isinstance check inside update_me() itself.
    with pytest.raises(Exception):
        MeUpdateRequest(command_palette_actions=[1, 2])


def test_update_welcome_back_settings(alice):
    update_me(
        MeUpdateRequest(welcome_back_ai_summary_enabled=True, welcome_back_threshold_days=14),
        alice,
        _rl=None,
    )
    from services.auth_service import get_user_by_id

    updated = get_user_by_id(alice["id"])
    result = me(updated)
    assert result["welcome_back_ai_summary_enabled"] is True
    assert result["welcome_back_threshold_days"] == 14


def test_welcome_back_threshold_days_out_of_range_rejected():
    with pytest.raises(Exception):
        MeUpdateRequest(welcome_back_threshold_days=0)
    with pytest.raises(Exception):
        MeUpdateRequest(welcome_back_threshold_days=91)


def test_update_tasks_filter_and_sort_mode(alice):
    update_me(
        MeUpdateRequest(tasks_filter="overdue", tasks_sort_mode="alpha"),
        alice,
        _rl=None,
    )
    from services.auth_service import get_user_by_id

    updated = get_user_by_id(alice["id"])
    result = me(updated)
    assert result["tasks_filter"] == "overdue"
    assert result["tasks_sort_mode"] == "alpha"


def test_invalid_tasks_filter_rejected(alice):
    with pytest.raises(HTTPException) as exc:
        update_me(MeUpdateRequest(tasks_filter="bogus"), alice, _rl=None)
    assert exc.value.status_code == 400


def test_invalid_tasks_sort_mode_rejected(alice):
    with pytest.raises(HTTPException) as exc:
        update_me(MeUpdateRequest(tasks_sort_mode="bogus"), alice, _rl=None)
    assert exc.value.status_code == 400
