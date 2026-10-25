"""The 9 task agent tools act in the caller's ACTIVE workspace. Until
2026-10-25 they ignored the `workspace` the dispatcher passes and always used
PERSONAL tasks — so the in-app AI in the Business workspace (and a
per-workspace MCP grant) read and wrote the wrong list."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from module_packages.tasks.backend.agent_tools import execute
from services import task_service

USER = {"name": "Alice"}


def _titles(tasks):
    return {t["title"] for t in tasks}


def test_add_and_list_stay_in_their_workspace(brain):
    execute("add_task", {"title": "Work", "category": "Work"}, USER, "business")
    execute("add_task", {"title": "Home", "category": "Home"}, USER, "personal")
    assert _titles(execute("list_tasks", {}, USER, "business")) == {"Work"}
    assert _titles(execute("list_tasks", {}, USER, "personal")) == {"Home"}
    assert _titles(task_service.list_tasks("Alice", "business")) == {"Work"}


def test_update_and_delete_only_touch_the_given_workspace(brain):
    task = execute("add_task", {"title": "Work", "category": "Work"}, USER, "business")
    missing = execute("update_task", {"task_id": task["id"], "title": "x"}, USER, "personal")
    assert "error" in missing
    updated = execute("update_task", {"task_id": task["id"], "title": "Work 2"}, USER, "business")
    assert updated["title"] == "Work 2"
    assert execute("delete_task", {"task_id": task["id"]}, USER, "personal") == {"deleted": False}
    assert execute("delete_task", {"task_id": task["id"]}, USER, "business") == {"deleted": True}


def test_bulk_create_scoring_and_snapshot_use_the_workspace(brain):
    execute(
        "create_tasks",
        {"tasks": [{"title": "A", "category": "Work"}, {"title": "B", "category": "Work"}]},
        USER,
        "business",
    )
    assert _titles(execute("get_scored_tasks", {}, USER, "business")) == {"A", "B"}
    assert execute("get_scored_tasks", {}, USER, "personal") == []
    assert _titles(execute("get_top3_tasks", {}, USER, "business")) == {"A", "B"}
    snapshot = execute("get_week_snapshot", {}, USER, "business")
    assert _titles(snapshot["no_date"]) == {"A", "B"}
    assert execute("get_week_snapshot", {}, USER, "personal")["no_date"] == []
