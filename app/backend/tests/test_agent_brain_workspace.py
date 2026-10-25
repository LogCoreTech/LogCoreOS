"""The agent's Brain file tools keep to the active workspace (2026-10-25).
The business root is nested inside the personal one (USERS/{name}/Business/),
so a personal list/read/search used to walk straight into business files, and
write/create resolved paths against the personal root even in business."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agent_service import _execute_tool
from services.file_service import user_path, write_markdown

USER = {"name": "Alice", "disabled_modules": []}


def _seed():
    base = user_path("Alice")
    write_markdown(base / "Notes" / "home.md", "personal note")
    write_markdown(base / "Business" / "Notes" / "work.md", "business note")


def test_personal_list_and_search_skip_business(brain):
    _seed()
    paths = {f["path"] for f in _execute_tool("list_brain_files", {}, USER, "personal")}
    assert "Notes/home.md" in paths
    assert not any(p.startswith("Business") for p in paths)
    hits = _execute_tool("search_brain", {"query": "business note"}, USER, "personal")
    assert not hits


def test_personal_read_cannot_reach_into_business(brain):
    _seed()
    denied = _execute_tool("read_brain_file", {"path": "Business/Notes/work.md"}, USER, "personal")
    assert denied == {"error": "Access denied"}
    ok = _execute_tool("read_brain_file", {"path": "Notes/work.md"}, USER, "business")
    assert "business note" in str(ok)


def test_business_write_and_create_land_in_business(brain):
    _seed()
    _execute_tool(
        "write_brain_file", {"path": "Notes/work.md", "content": "updated"}, USER, "business"
    )
    assert "updated" in (user_path("Alice") / "Business" / "Notes" / "work.md").read_text()
    _execute_tool("create_brain_file", {"path": "Notes/new.md", "content": "n"}, USER, "business")
    assert (user_path("Alice") / "Business" / "Notes" / "new.md").exists()
    assert not (user_path("Alice") / "Notes" / "new.md").exists()


def test_personal_write_cannot_target_business_root(brain):
    _seed()
    result = _execute_tool(
        "write_brain_file", {"path": "Business/Notes/work.md", "content": "x"}, USER, "personal"
    )
    assert "error" in result
