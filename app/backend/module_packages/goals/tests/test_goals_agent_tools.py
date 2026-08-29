"""Tests for module_packages/goals/backend/agent_tools.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.goals.backend import agent_tools

USER = {"name": "Alice"}


def test_create_get_update_delete_goal(brain):
    created = agent_tools.execute("create_goal", {"title": "Ship v2"}, USER)
    assert created["title"] == "Ship v2"

    fetched = agent_tools.execute("get_goal", {"goal_id": created["id"]}, USER)
    assert fetched["goal"]["id"] == created["id"]
    assert "progress" in fetched

    updated = agent_tools.execute("update_goal", {"goal_id": created["id"], "status": "done"}, USER)
    assert updated["status"] == "done"

    result = agent_tools.execute("delete_goal", {"goal_id": created["id"]}, USER)
    assert result["deleted"] is True


def test_get_goal_missing_returns_error_not_raise(brain):
    result = agent_tools.execute("get_goal", {"goal_id": "nope"}, USER)
    assert "error" in result


def test_list_goals(brain):
    agent_tools.execute("create_goal", {"title": "A"}, USER)
    agent_tools.execute("create_goal", {"title": "B"}, USER)
    result = agent_tools.execute("list_goals", {}, USER)
    assert len(result) == 2


def test_link_and_unlink_task_to_goal(brain):
    from services import task_service

    goal = agent_tools.execute("create_goal", {"title": "Goal with tasks"}, USER)
    task = task_service.add_task("Alice", {"title": "Do the thing", "category": "Work"})

    linked = agent_tools.execute("link_task_to_goal", {"task_id": task["id"], "goal_id": goal["id"]}, USER)
    assert linked["goal_id"] == goal["id"]

    unlinked = agent_tools.execute("unlink_task_from_goal", {"task_id": task["id"]}, USER)
    assert unlinked["goal_id"] is None


def test_create_subgoal_via_parent_id(brain):
    root = agent_tools.execute("create_goal", {"title": "Root"}, USER)
    sub = agent_tools.execute("create_goal", {"title": "Sub", "parent_id": root["id"]}, USER)
    detail = agent_tools.execute("get_goal", {"goal_id": root["id"]}, USER)
    assert [g["id"] for g in detail["subgoals"]] == [sub["id"]]


def test_unknown_tool_name_returns_none(brain):
    assert agent_tools.execute("not_a_real_tool", {}, USER) is None
