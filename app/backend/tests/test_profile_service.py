"""Tests for services/profile_service.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import services.profile_service as svc

USER = "TestUser"


@pytest.fixture()
def user_dir(brain):
    d = brain / "USERS" / USER
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# load_profile
# ---------------------------------------------------------------------------


def test_load_profile_new_user_returns_dict(user_dir):
    data = svc.load_profile(USER)
    assert isinstance(data, dict)


def test_load_profile_reads_json(user_dir):
    svc.save_profile(USER, {"occupation": "Engineer"})
    data = svc.load_profile(USER)
    assert data["occupation"] == "Engineer"


def test_load_profile_seeds_from_profile_md(user_dir):
    (user_dir / "Profile.md").write_text(
        "## Life Priorities\n1. Health\n2. Work\n"
    )
    data = svc.load_profile(USER)
    assert data.get("priority_order") == ["Health", "Work"]


# ---------------------------------------------------------------------------
# save_profile
# ---------------------------------------------------------------------------


def test_save_profile_persists_to_json(user_dir):
    svc.save_profile(USER, {"occupation": "Baker"})
    assert (user_dir / "profile.json").exists()


def test_save_profile_generates_profile_md(user_dir):
    svc.save_profile(USER, {"occupation": "Developer"})
    assert (user_dir / "Profile.md").exists()


def test_save_profile_defaults_empty_priority_order(user_dir):
    data = svc.save_profile(USER, {})
    assert data["priority_order"] == svc.DEFAULT_PRIORITY_ORDER


def test_save_profile_preserves_custom_priority_order(user_dir):
    order = ["Health", "Family", "Work"]
    data = svc.save_profile(USER, {"priority_order": order})
    assert data["priority_order"] == order


# ---------------------------------------------------------------------------
# get_priority_order
# ---------------------------------------------------------------------------


def test_get_priority_order_from_json(user_dir):
    svc.save_profile(USER, {"priority_order": ["A", "B", "C"]})
    assert svc.get_priority_order(USER) == ["A", "B", "C"]


def test_get_priority_order_fallback_to_defaults(user_dir):
    # No profile.json — no Profile.md — returns defaults
    assert svc.get_priority_order(USER) == svc.DEFAULT_PRIORITY_ORDER


def test_get_priority_order_fallback_to_profile_md(user_dir):
    (user_dir / "Profile.md").write_text(
        "## Life Priorities\n1. God\n2. Family\n"
    )
    order = svc.get_priority_order(USER)
    assert order == ["God", "Family"]


# ---------------------------------------------------------------------------
# generate_profile_md
# ---------------------------------------------------------------------------


def test_generate_md_always_has_life_priorities(user_dir):
    md = svc.generate_profile_md(USER, {})
    assert "## Life Priorities" in md


def test_generate_md_includes_username(user_dir):
    md = svc.generate_profile_md(USER, {})
    assert USER in md


def test_generate_md_skips_empty_sections(user_dir):
    md = svc.generate_profile_md(USER, {})
    for absent in ("## Daily Routine", "## Health", "## Work & Career", "## Family"):
        assert absent not in md


def test_generate_md_includes_occupation(user_dir):
    md = svc.generate_profile_md(USER, {"occupation": "Baker"})
    assert "Baker" in md


def test_generate_md_includes_children(user_dir):
    md = svc.generate_profile_md(USER, {"children": [{"name": "Alice", "age": "5"}]})
    assert "Alice" in md


def test_generate_md_custom_priority_order(user_dir):
    md = svc.generate_profile_md(USER, {"priority_order": ["Health", "Family"]})
    assert "1. Health" in md
    assert "2. Family" in md


def test_generate_md_ai_preferences(user_dir):
    md = svc.generate_profile_md(USER, {"tone": "concise", "communication_style": "direct"})
    assert "## AI Preferences" in md
    assert "concise" in md
