"""Tests for core file I/O utilities in services/file_service.py."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services.file_service import (
    history_path,
    parse_priority_order,
    profile_path,
    read_json,
    resolve_user_md_path,
    tasks_path,
    user_path,
    write_json,
)

USER = "TestUser"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def test_user_path(brain):
    assert user_path(USER) == brain / "USERS" / USER


def test_tasks_path(brain):
    assert tasks_path(USER) == brain / "USERS" / USER / "Tasks" / "tasks.json"


def test_history_path(brain):
    assert history_path(USER) == brain / "USERS" / USER / "Tasks" / "tasks_history.json"


def test_profile_path(brain):
    assert profile_path(USER) == brain / "USERS" / USER / "Profile.md"


# ---------------------------------------------------------------------------
# read_json
# ---------------------------------------------------------------------------


def test_read_json_missing_returns_default(brain):
    assert read_json(brain / "ghost.json", default={"k": "v"}) == {"k": "v"}


def test_read_json_missing_no_default_returns_empty_dict(brain):
    assert read_json(brain / "ghost.json") == {}


def test_read_json_empty_file_returns_default(brain):
    p = brain / "empty.json"
    p.write_text("")
    assert read_json(p, default={"a": 1}) == {"a": 1}


def test_read_json_malformed_returns_default(brain):
    p = brain / "bad.json"
    p.write_text("{not valid json}")
    assert read_json(p, default={"fallback": True}) == {"fallback": True}


def test_read_json_malformed_no_default_returns_empty_dict(brain):
    p = brain / "bad.json"
    p.write_text("{not valid json}")
    assert read_json(p) == {}


def test_read_json_valid(brain):
    p = brain / "data.json"
    p.write_text(json.dumps({"tasks": [1, 2, 3]}))
    assert read_json(p) == {"tasks": [1, 2, 3]}


# ---------------------------------------------------------------------------
# write_json
# ---------------------------------------------------------------------------


def test_write_json_creates_file(brain):
    p = brain / "out.json"
    write_json(p, {"hello": "world"})
    assert p.exists()
    assert json.loads(p.read_text()) == {"hello": "world"}


def test_write_json_creates_parent_dirs(brain):
    p = brain / "deep" / "nested" / "file.json"
    write_json(p, {"x": 1})
    assert p.exists()


def test_write_json_round_trip(brain):
    p = brain / "rt.json"
    payload = {"tasks": [{"id": "abc", "title": "Test"}]}
    write_json(p, payload)
    assert read_json(p) == payload


def test_write_json_overwrites_existing(brain):
    p = brain / "overwrite.json"
    write_json(p, {"v": 1})
    write_json(p, {"v": 2})
    assert read_json(p) == {"v": 2}


# ---------------------------------------------------------------------------
# resolve_user_md_path
# ---------------------------------------------------------------------------


def test_resolve_valid_path(brain):
    (brain / "USERS" / USER).mkdir(parents=True)
    p = resolve_user_md_path(USER, "Profile.md")
    assert p.name == "Profile.md"


def test_resolve_nested_path(brain):
    (brain / "USERS" / USER).mkdir(parents=True)
    p = resolve_user_md_path(USER, "Notes/ideas.md")
    assert p.name == "ideas.md"


def test_resolve_rejects_traversal(brain):
    with pytest.raises(ValueError):
        resolve_user_md_path(USER, "../OtherUser/Profile.md")


def test_resolve_rejects_non_md(brain):
    with pytest.raises(ValueError):
        resolve_user_md_path(USER, "tasks.json")


def test_resolve_rejects_double_dot_segment(brain):
    with pytest.raises(ValueError):
        resolve_user_md_path(USER, "a/../b.md")


def test_resolve_rejects_empty_segment(brain):
    with pytest.raises(ValueError):
        resolve_user_md_path(USER, "")


def test_resolve_rejects_dot_segment(brain):
    with pytest.raises(ValueError):
        resolve_user_md_path(USER, "./Profile.md")


def test_resolve_rejects_invalid_chars(brain):
    with pytest.raises(ValueError):
        resolve_user_md_path(USER, "notes/bad;name.md")


# ---------------------------------------------------------------------------
# parse_priority_order
# ---------------------------------------------------------------------------


def test_parse_priority_order_extracts_items(brain):
    user_dir = brain / "USERS" / USER
    user_dir.mkdir(parents=True)
    (user_dir / "Profile.md").write_text(
        "# Profile\n\n## Life Priorities\n1. God\n2. Family\n3. Job\n\n## Other\nstuff\n"
    )
    assert parse_priority_order(USER) == ["God", "Family", "Job"]


def test_parse_priority_order_stops_at_next_heading(brain):
    user_dir = brain / "USERS" / USER
    user_dir.mkdir(parents=True)
    (user_dir / "Profile.md").write_text(
        "## Life Priorities\n1. Health\n2. Work\n\n## Something Else\n3. Noise\n"
    )
    order = parse_priority_order(USER)
    assert "Noise" not in order
    assert order == ["Health", "Work"]


def test_parse_priority_order_missing_section_returns_empty(brain):
    user_dir = brain / "USERS" / USER
    user_dir.mkdir(parents=True)
    (user_dir / "Profile.md").write_text("# Profile\n\nNo priorities here.\n")
    assert parse_priority_order(USER) == []
