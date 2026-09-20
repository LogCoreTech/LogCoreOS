"""Tests for module_packages/homes/backend/agent_tools.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from module_packages.homes.backend import agent_tools

USER = {"name": "Alice"}


def test_create_get_update_delete_home(brain):
    created = agent_tools.execute("create_home", {"name": "Cabin", "ownership_type": "own"}, USER)
    assert created["name"] == "Cabin"
    assert created["tag"].startswith("home:")

    fetched = agent_tools.execute("get_home", {"home_id": created["id"]}, USER)
    assert fetched["id"] == created["id"]

    updated = agent_tools.execute(
        "update_home", {"home_id": created["id"], "name": "Lake Cabin"}, USER
    )
    assert updated["name"] == "Lake Cabin"
    assert updated["tag"] == created["tag"]  # frozen on rename

    result = agent_tools.execute("delete_home", {"home_id": created["id"]}, USER)
    assert result["deleted"] is True


def test_get_home_missing_returns_error_not_raise(brain):
    result = agent_tools.execute("get_home", {"home_id": "nope"}, USER)
    assert "error" in result


def test_create_home_invalid_returns_error_not_raise(brain):
    result = agent_tools.execute("create_home", {"name": "X", "ownership_type": "condo"}, USER)
    assert "error" in result


def test_list_homes(brain):
    agent_tools.execute("create_home", {"name": "A", "ownership_type": "rent"}, USER)
    agent_tools.execute("create_home", {"name": "B", "ownership_type": "own"}, USER)
    result = agent_tools.execute("list_homes", {}, USER)
    assert len(result) == 2
