"""Tests for search_service.py's 2026-09-04 UX Polish Batch item #10
additions: cross-workspace search, per-provider "show more", and the
with_totals opt-in response shape. Kept separate from test_search_service.py
(that file's own 17 tests already cover the pre-existing default-shape
contract and must stay passing unchanged)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import auth_service, mod_store_service, task_service

USER = "SearchUser2"


@pytest.fixture()
def user_brain(brain):
    (brain / "USERS" / USER / "Tasks").mkdir(parents=True, exist_ok=True)
    auth_service.create_user("search2@example.com", "password123", USER)
    mod_store_service.mark_installed("tasks", by="test")
    mod_store_service.mark_installed("goals", by="test")
    return brain


def _user(workspaces=None, disabled_modules=None):
    return {
        "name": USER,
        "disabled_modules": disabled_modules or [],
        "workspaces": workspaces or ["personal", "business"],
    }


def test_default_shape_is_still_a_plain_list(user_brain):
    from services import search_service

    task_service.add_task(USER, {"title": "Renew passport", "category": "Errands"})

    results = search_service.search("passport", [], _user(), "personal")
    assert isinstance(results, list)


def test_with_totals_returns_dict_shape(user_brain):
    from services import search_service

    task_service.add_task(USER, {"title": "Renew passport", "category": "Errands"})

    result = search_service.search("passport", [], _user(), "personal", with_totals=True)
    assert set(result.keys()) == {"results", "provider_totals"}
    assert result["provider_totals"]["tasks:tasks"] == 1


def test_cross_workspace_searches_both_and_tags_each_result(user_brain):
    from services import search_service

    task_service.add_task(USER, {"title": "Personal report"}, "personal")
    task_service.add_task(USER, {"title": "Business report"}, "business")

    results = search_service.search("report", [], _user(), "personal", cross_workspace=True)
    by_title = {r["title"]: r["_workspace"] for r in results}
    assert by_title["Personal report"] == "personal"
    assert by_title["Business report"] == "business"


def test_without_cross_workspace_only_searches_active_workspace(user_brain):
    from services import search_service

    task_service.add_task(USER, {"title": "Personal report"}, "personal")
    task_service.add_task(USER, {"title": "Business report"}, "business")

    results = search_service.search("report", [], _user(), "personal", cross_workspace=False)
    titles = [r["title"] for r in results]
    assert "Personal report" in titles
    assert "Business report" not in titles


def test_every_result_carries_workspace_even_without_cross_workspace(user_brain):
    from services import search_service

    task_service.add_task(USER, {"title": "Renew passport"}, "personal")

    results = search_service.search("passport", [], _user(), "personal")
    assert results[0]["_workspace"] == "personal"


def test_provider_show_more_narrows_to_one_provider_at_higher_cap(user_brain):
    from services import search_service

    for i in range(30):
        task_service.add_task(USER, {"title": f"Errand {i}"})

    default = search_service.search("Errand", [], _user(), "personal", with_totals=True)
    assert len(default["results"]) == 20  # _PER_PROVIDER_CAP
    assert default["provider_totals"]["tasks:tasks"] == 30

    more = search_service.search(
        "Errand", [], _user(), "personal", provider="tasks:tasks", with_totals=True
    )
    assert len(more["results"]) == 30  # under _SHOW_MORE_CAP, all returned
    assert all(r["_module"] == "tasks" for r in more["results"])


def test_provider_show_more_ignores_other_providers(user_brain):
    from module_packages.goals.backend.service import create_goal
    from services import search_service

    task_service.add_task(USER, {"title": "Shared word task"})
    create_goal(USER, {"title": "Shared word goal"})

    result = search_service.search(
        "Shared word", [], _user(), "personal", provider="tasks:tasks", with_totals=True
    )
    assert all(r["_module"] == "tasks" for r in result["results"])
    assert "goals:goals" not in result["provider_totals"]
