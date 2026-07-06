"""Tests for task scoring logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import auth_service
from services.file_service import tasks_path, user_path, write_json
from services.priority_service import get_all_scored, get_top3, score_task

ORDER = ["God", "Family", "Job", "Personal Growth", "Hobbies"]


def _task(category="God", priority="High", due_date=None):
    return {"category": category, "priority": priority, "due_date": due_date}


def test_highest_score_first_category_high_priority():
    # cat_weight = 5 (len - idx 0), pri_weight = 3 → 15
    assert score_task(_task("God", "High"), ORDER, "2024-06-01") == 15


def test_lower_category_scores_less():
    s1 = score_task(_task("God", "High"), ORDER, "2024-06-01")
    s2 = score_task(_task("Hobbies", "High"), ORDER, "2024-06-01")
    assert s1 > s2


def test_higher_priority_scores_more_same_category():
    s_high = score_task(_task("Job", "High"), ORDER, "2024-06-01")
    s_low = score_task(_task("Job", "Low"), ORDER, "2024-06-01")
    assert s_high > s_low


def test_overdue_adds_10_urgency():
    base = score_task(_task("God", "High"), ORDER, "2024-06-01")
    overdue = score_task(_task("God", "High", "2024-05-31"), ORDER, "2024-06-01")
    assert overdue - base == 10


def test_due_today_adds_5():
    base = score_task(_task("God", "High"), ORDER, "2024-06-01")
    today = score_task(_task("God", "High", "2024-06-01"), ORDER, "2024-06-01")
    assert today - base == 5


def test_due_within_week_adds_2():
    base = score_task(_task("God", "High"), ORDER, "2024-06-01")
    soon = score_task(_task("God", "High", "2024-06-07"), ORDER, "2024-06-01")
    assert soon - base == 2


def test_unknown_category_gets_zero_score():
    # cat_weight=0 → 0 * pri_weight = 0; no urgency
    assert score_task(_task("Unknown", "High"), ORDER, "2024-06-01") == 0


def test_medium_priority_weight():
    # cat_weight=5, pri_weight=2 → 10
    assert score_task(_task("God", "Medium"), ORDER, "2024-06-01") == 10


# ---------------------------------------------------------------------------
# get_top3 / get_all_scored (integration — requires filesystem + auth)
# ---------------------------------------------------------------------------

PRIORITY_USER = "PriorityUser"


def _seed_tasks(brain, tasks: list[dict]) -> None:
    user_dir = brain / "USERS" / PRIORITY_USER
    tasks_dir = user_dir / "Tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    from services.profile_service import save_profile

    save_profile(PRIORITY_USER, {"priority_order": ORDER})
    rows = [
        {
            "id": str(i),
            "title": t.get("title", f"Task {i}"),
            "category": t.get("category", "God"),
            "priority": t.get("priority", "High"),
            "status": t.get("status", "pending"),
            "type": "todo",
            "due_date": t.get("due_date"),
            "created_at": "2024-06-01T00:00:00",
        }
        for i, t in enumerate(tasks)
    ]
    write_json(tasks_path(PRIORITY_USER), {"tasks": rows})


@pytest.fixture()
def priority_brain(brain):
    auth_service.create_user("priority@example.com", "pw", PRIORITY_USER)
    return brain


def test_get_top3_returns_at_most_three(priority_brain):
    _seed_tasks(priority_brain, [{"title": f"T{i}"} for i in range(5)])
    assert len(get_top3(PRIORITY_USER)) <= 3


def test_get_top3_returns_fewer_when_fewer_tasks(priority_brain):
    _seed_tasks(priority_brain, [{"title": "Only"}])
    assert len(get_top3(PRIORITY_USER)) == 1


def test_get_top3_attaches_score(priority_brain):
    _seed_tasks(priority_brain, [{"title": "T"}])
    top = get_top3(PRIORITY_USER)
    assert "_score" in top[0]


def test_get_top3_excludes_done_tasks(priority_brain):
    _seed_tasks(
        priority_brain,
        [
            {"title": "done", "status": "done"},
            {"title": "pending", "status": "pending"},
        ],
    )
    top = get_top3(PRIORITY_USER)
    assert all(t.get("status", "pending") == "pending" for t in top)


def test_get_all_scored_sorted_descending(priority_brain):
    _seed_tasks(
        priority_brain,
        [
            {"title": "Low", "category": "Hobbies", "priority": "Low"},
            {"title": "High", "category": "God", "priority": "High"},
            {"title": "Mid", "category": "Job", "priority": "Medium"},
        ],
    )
    scored = get_all_scored(PRIORITY_USER)
    scores = [t["_score"] for t in scored]
    assert scores == sorted(scores, reverse=True)


def test_get_all_scored_only_pending(priority_brain):
    _seed_tasks(
        priority_brain,
        [
            {"title": "done", "status": "done"},
            {"title": "pending", "status": "pending"},
        ],
    )
    scored = get_all_scored(PRIORITY_USER)
    assert all(t.get("status", "pending") == "pending" for t in scored)
