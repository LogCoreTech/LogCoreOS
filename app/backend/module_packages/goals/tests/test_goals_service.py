"""Tests for module_packages/goals/backend/service.py — CRUD, hierarchy
(nesting/cycle-guard), delete choices, progress rollup, and metric
resolution. The core, highest-risk logic of this brand-new module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.goals.backend import service as goals_service

USER = "Alice"


@pytest.fixture()
def user():
    return {"name": USER}


def _mk(title="Goal", **kw):
    data = {"title": title, "category": "Health"}
    data.update(kw)
    return goals_service.create_goal(USER, data)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_and_get_goal(brain):
    g = _mk("Run a marathon")
    assert g["title"] == "Run a marathon"
    assert g["status"] == "pending"
    assert g["parent_id"] is None
    fetched = goals_service.get_goal(USER, g["id"])
    assert fetched["id"] == g["id"]


def test_due_date_is_fully_optional(brain):
    g = goals_service.create_goal(USER, {"title": "No due date"})
    assert g["due_date"] is None


def test_update_goal(brain):
    g = _mk()
    updated = goals_service.update_goal(USER, g["id"], {"title": "Renamed", "status": "done"})
    assert updated["title"] == "Renamed"
    assert updated["status"] == "done"


def test_update_nonexistent_goal_returns_none(brain):
    assert goals_service.update_goal(USER, "nope", {"title": "x"}) is None


# ---------------------------------------------------------------------------
# Hierarchy — unbounded nesting, cycle guard
# ---------------------------------------------------------------------------


def test_create_subgoal(brain):
    parent = _mk("Life goal")
    child = _mk("Subgoal", parent_id=parent["id"])
    assert child["parent_id"] == parent["id"]
    assert goals_service.get_subgoals(USER, parent["id"]) == [child]


def test_create_with_missing_parent_raises(brain):
    with pytest.raises(ValueError):
        goals_service.create_goal(USER, {"title": "Orphan", "parent_id": "does-not-exist"})


def test_arbitrary_depth_nesting(brain):
    root = _mk("Root")
    a = _mk("A", parent_id=root["id"])
    b = _mk("B", parent_id=a["id"])
    c = _mk("C", parent_id=b["id"])
    subtree = goals_service.collect_subtree_ids(goals_service.list_goals(USER), root["id"])
    assert subtree == {root["id"], a["id"], b["id"], c["id"]}


def test_cannot_reparent_goal_under_its_own_descendant(brain):
    root = _mk("Root")
    child = _mk("Child", parent_id=root["id"])
    with pytest.raises(ValueError):
        goals_service.update_goal(USER, root["id"], {"parent_id": child["id"]})


def test_get_root_goals_excludes_subgoals(brain):
    root = _mk("Root")
    _mk("Child", parent_id=root["id"])
    roots = goals_service.get_root_goals(USER)
    assert [g["id"] for g in roots] == [root["id"]]


# ---------------------------------------------------------------------------
# Linked tasks
# ---------------------------------------------------------------------------


def test_get_linked_tasks(brain):
    from services import task_service

    g = _mk("Ship it")
    t = task_service.add_task(
        USER, {"title": "Write tests", "category": "Work", "goal_id": g["id"]}
    )
    linked = goals_service.get_linked_tasks(USER, g["id"])
    assert [x["id"] for x in linked] == [t["id"]]


# ---------------------------------------------------------------------------
# Delete — scope + linked-task choices
# ---------------------------------------------------------------------------


def test_delete_without_cascade_reparents_subgoals(brain):
    root = _mk("Root")
    mid = _mk("Mid", parent_id=root["id"])
    leaf = _mk("Leaf", parent_id=mid["id"])

    result = goals_service.delete_goal(USER, mid["id"], cascade=False)
    assert result["deleted_goal_ids"] == [mid["id"]]

    leaf_after = goals_service.get_goal(USER, leaf["id"])
    assert leaf_after["parent_id"] == root["id"]  # reparented up, not orphaned


def test_delete_with_cascade_removes_whole_subtree(brain):
    root = _mk("Root")
    mid = _mk("Mid", parent_id=root["id"])
    leaf = _mk("Leaf", parent_id=mid["id"])

    result = goals_service.delete_goal(USER, mid["id"], cascade=True)
    assert set(result["deleted_goal_ids"]) == {mid["id"], leaf["id"]}
    assert goals_service.get_goal(USER, leaf["id"]) is None
    assert goals_service.get_goal(USER, root["id"]) is not None  # untouched


def test_delete_nonexistent_goal_returns_none(brain):
    assert goals_service.delete_goal(USER, "nope") is None


def test_delete_default_unlinks_tasks_without_deleting_them(brain):
    from services import task_service

    g = _mk("Goal with a task")
    t = task_service.add_task(USER, {"title": "Linked", "category": "Work", "goal_id": g["id"]})

    result = goals_service.delete_goal(USER, g["id"])
    assert result["affected_task_ids"] == [t["id"]]

    still_there = task_service.get_task(USER, t["id"])
    assert still_there is not None
    assert still_there.get("goal_id") is None


def test_delete_with_delete_linked_tasks_true_deletes_them(brain):
    from services import task_service

    g = _mk("Goal with a task")
    t = task_service.add_task(USER, {"title": "Linked", "category": "Work", "goal_id": g["id"]})

    goals_service.delete_goal(USER, g["id"], delete_linked_tasks=True)

    assert task_service.get_task(USER, t["id"]) is None


# ---------------------------------------------------------------------------
# Progress: manual, rollup (weighted average), metric-wins-over-rollup
# ---------------------------------------------------------------------------


def test_manual_goal_with_no_children_is_binary(user, brain):
    g = _mk("Plain")
    progress = goals_service.compute_progress(USER, g, "personal", user)
    assert progress == {"source": "manual", "pct": 0, "current": None, "target": None}

    goals_service.update_goal(USER, g["id"], {"status": "done"})
    g_done = goals_service.get_goal(USER, g["id"])
    progress = goals_service.compute_progress(USER, g_done, "personal", user)
    assert progress["pct"] == 100


def test_rollup_is_weighted_average_of_children(user, brain):
    from services import task_service

    root = _mk("Root")
    sub = _mk("Sub", parent_id=root["id"])
    goals_service.update_goal(USER, sub["id"], {"status": "done"})  # sub = 100%
    task_service.add_task(USER, {"title": "T1", "category": "Work", "goal_id": root["id"]})  # 0%

    goals = goals_service.list_goals(USER)
    root_fresh = next(g for g in goals if g["id"] == root["id"])
    progress = goals_service.compute_progress(USER, root_fresh, "personal", user, goals)
    assert progress["source"] == "rollup"
    assert progress["pct"] == 50  # (100 + 0) / 2


def test_metric_wins_over_rollup_when_both_present(user, brain):
    from services import task_service

    root = _mk(
        "Root",
        metric={
            "provider": "manual",
            "config": {"target_value": 10},
            "history": [{"date": "2026-01-01", "value": 5}],
        },
    )
    task_service.add_task(
        USER, {"title": "T1", "category": "Work", "goal_id": root["id"], "status": "done"}
    )

    goals = goals_service.list_goals(USER)
    root_fresh = next(g for g in goals if g["id"] == root["id"])
    progress = goals_service.compute_progress(USER, root_fresh, "personal", user, goals)
    assert progress["source"] == "metric"
    assert progress["pct"] == 50  # 5/10, NOT the linked task's 100%


def test_manual_metric_uses_latest_logged_value(brain):
    g = _mk("Pages read goal", metric={"provider": "manual", "config": {"target_value": 200}})
    goals_service.log_manual_value(USER, g["id"], 40, when="2026-01-01")
    goals_service.log_manual_value(USER, g["id"], 90, when="2026-01-08")
    fresh = goals_service.get_goal(USER, g["id"])
    assert fresh["metric"]["history"][-1]["value"] == 90

    progress = goals_service.compute_progress(USER, fresh, "personal", {"name": USER})
    assert progress["pct"] == round(90 * 100 / 200)


def test_manual_metric_pct_clamps_at_100_when_current_exceeds_target(brain):
    g = _mk("Overshot goal", metric={"provider": "manual", "config": {"target_value": 150}})
    goals_service.log_manual_value(USER, g["id"], 160, when="2026-01-01")
    fresh = goals_service.get_goal(USER, g["id"])
    progress = goals_service.compute_progress(USER, fresh, "personal", {"name": USER})
    assert progress["pct"] == 100


def test_unknown_metric_provider_degrades_to_zero_not_crash(user, brain):
    g = _mk("Broken metric", metric={"provider": "not:a-real-provider", "config": {}})
    progress = goals_service.compute_progress(USER, g, "personal", user)
    assert progress == {"source": "metric", "current": 0, "target": None, "pct": 0}


# ---------------------------------------------------------------------------
# On-pace
# ---------------------------------------------------------------------------


def test_on_pace_none_without_metric_and_due_date(brain):
    g = _mk("No metric")
    progress = {"source": "manual", "pct": 0, "current": None, "target": None}
    assert goals_service.on_pace(g, progress) is None


# ---------------------------------------------------------------------------
# Migration helper (pure function)
# ---------------------------------------------------------------------------


def test_goal_from_legacy_task_preserves_core_fields():
    task = {
        "id": "abc",
        "title": "Old goal",
        "category": "Work",
        "due_date": "2026-12-31",
        "status": "pending",
        "notes": "note",
        "created_by": "Alice",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    goal = goals_service.goal_from_legacy_task(task)
    assert goal["id"] == "abc"
    assert goal["title"] == "Old goal"
    assert goal["due_date"] == "2026-12-31"
    assert goal["parent_id"] is None
    assert goal["metric"] is None


# ---------------------------------------------------------------------------
# Recurring-task completion-rate rollup contribution (2026-08-29, owner ask)
# ---------------------------------------------------------------------------


def test_recurring_linked_task_contributes_completion_rate_not_binary(user, brain):
    from datetime import date, timedelta

    from services import task_service

    root = _mk("Habit goal")
    task = task_service.add_task(
        USER,
        {
            "title": "Meditate",
            "category": "Health",
            "type": "recurring",
            "recurrence": "daily",
            "goal_id": root["id"],
            "counts_toward_goal": True,
        },
    )
    # Manually seed a completion_log with 15 of the last 30 days completed —
    # a real "done" toggle only ever adds today's date, so this simulates a
    # task that's been running for a while.
    log = [{"date": (date.today() - timedelta(days=i)).isoformat()} for i in range(0, 30, 2)]
    task_service.update_task(USER, task["id"], {"completion_log": log})

    goals = goals_service.list_goals(USER)
    root_fresh = next(g for g in goals if g["id"] == root["id"])
    progress = goals_service.compute_progress(USER, root_fresh, "personal", user, goals)
    assert progress["source"] == "rollup"
    # 15 entries in a 30-day window = 50%, and it's the ONLY child, so the
    # rollup average equals that rate directly.
    assert progress["pct"] == 50


def test_recurring_linked_task_with_no_completions_contributes_zero(user, brain):
    from services import task_service

    root = _mk("Fresh habit goal")
    task_service.add_task(
        USER,
        {
            "title": "New habit",
            "category": "Health",
            "type": "recurring",
            "recurrence": "daily",
            "goal_id": root["id"],
            "counts_toward_goal": True,
        },
    )
    goals = goals_service.list_goals(USER)
    root_fresh = next(g for g in goals if g["id"] == root["id"])
    progress = goals_service.compute_progress(USER, root_fresh, "personal", user, goals)
    assert progress["source"] == "rollup"
    assert progress["pct"] == 0


def test_non_recurring_linked_task_still_uses_binary_contribution(user, brain):
    from services import task_service

    root = _mk("Mixed goal")
    t = task_service.add_task(
        USER, {"title": "One-off", "category": "Health", "goal_id": root["id"]}
    )
    task_service.update_task(USER, t["id"], {"status": "done"})
    goals = goals_service.list_goals(USER)
    root_fresh = next(g for g in goals if g["id"] == root["id"])
    progress = goals_service.compute_progress(USER, root_fresh, "personal", user, goals)
    assert progress["pct"] == 100


def test_recurring_task_not_counting_toward_goal_is_excluded_from_rollup(user, brain):
    from datetime import date, timedelta

    from services import task_service

    root = _mk("Opt-out habit goal")
    task = task_service.add_task(
        USER,
        {
            "title": "Journaling",
            "category": "Health",
            "type": "recurring",
            "recurrence": "daily",
            "goal_id": root["id"],
            "counts_toward_goal": False,
        },
    )
    log = [{"date": (date.today() - timedelta(days=i)).isoformat()} for i in range(0, 30, 2)]
    task_service.update_task(USER, task["id"], {"completion_log": log})

    goals = goals_service.list_goals(USER)
    root_fresh = next(g for g in goals if g["id"] == root["id"])
    progress = goals_service.compute_progress(USER, root_fresh, "personal", user, goals)
    # Excluded task is the only child, so nothing contributes to the rollup —
    # falls back to the manual pending/done toggle instead.
    assert progress["source"] == "manual"
    assert progress["pct"] == 0


def test_recurring_rollup_excludes_missed_log_entries(user, brain):
    """A 'missed' entry (2026-08-30, auto-logged by the nightly job) must not
    inflate the completion rate the way a completed entry would."""
    from datetime import date, timedelta

    from services import task_service

    root = _mk("Missed-aware habit goal")
    task = task_service.add_task(
        USER,
        {
            "title": "Stretch",
            "category": "Health",
            "type": "recurring",
            "recurrence": "daily",
            "goal_id": root["id"],
            "counts_toward_goal": True,
        },
    )
    # 30 entries, all in the trailing window, half "completed" half "missed".
    log = [
        {
            "date": (date.today() - timedelta(days=i)).isoformat(),
            "status": "completed" if i % 2 == 0 else "missed",
        }
        for i in range(30)
    ]
    task_service.update_task(USER, task["id"], {"completion_log": log})

    goals = goals_service.list_goals(USER)
    root_fresh = next(g for g in goals if g["id"] == root["id"])
    progress = goals_service.compute_progress(USER, root_fresh, "personal", user, goals)
    assert progress["source"] == "rollup"
    # 15 of 30 are "completed" — same 50% a pre-status-field log with 15
    # entries would have produced, confirming "missed" entries are excluded
    # rather than silently counted.
    assert progress["pct"] == 50


def test_recurring_rollup_mixed_completed_missed_and_legacy_entries(user, brain):
    """A log with real 'completed', real 'missed', and legacy no-status
    entries all in the same window — legacy entries must count exactly like
    'completed' ones."""
    from datetime import date, timedelta

    from services import task_service

    root = _mk("Mixed-log habit goal")
    task = task_service.add_task(
        USER,
        {
            "title": "Read",
            "category": "Personal",
            "type": "recurring",
            "recurrence": "daily",
            "goal_id": root["id"],
            "counts_toward_goal": True,
        },
    )
    log = []
    for i in range(30):
        entry = {"date": (date.today() - timedelta(days=i)).isoformat()}
        if i < 10:
            entry["status"] = "completed"
        elif i < 20:
            entry["status"] = "missed"
        # else: legacy entry, no "status" key at all — should count like "completed"
        log.append(entry)
    task_service.update_task(USER, task["id"], {"completion_log": log})

    goals = goals_service.list_goals(USER)
    root_fresh = next(g for g in goals if g["id"] == root["id"])
    progress = goals_service.compute_progress(USER, root_fresh, "personal", user, goals)
    assert progress["source"] == "rollup"
    # 10 "completed" + 10 legacy (counts) = 20 of 30 = ~67%
    assert progress["pct"] == round(20 * 100 / 30)


def test_recurring_task_default_missing_field_still_counts(user, brain):
    """A recurring task linked before this feature shipped has no
    counts_toward_goal key at all — must keep counting (backward compat),
    not silently opt out."""
    from services import task_service

    root = _mk("Legacy habit goal")
    task = task_service.add_task(
        USER,
        {"title": "Old habit", "category": "Health", "type": "recurring", "recurrence": "daily"},
    )
    task_service.update_task(USER, task["id"], {"goal_id": root["id"], "counts_toward_goal": True})
    # Simulate legacy data by stripping the field back off directly.
    from services import file_service

    def _strip(data):
        for t in data["tasks"]:
            if t["id"] == task["id"]:
                t.pop("counts_toward_goal", None)
        return data

    file_service.update_json(file_service.tasks_path(USER), _strip, default={"tasks": []})

    goals = goals_service.list_goals(USER)
    root_fresh = next(g for g in goals if g["id"] == root["id"])
    progress = goals_service.compute_progress(USER, root_fresh, "personal", user, goals)
    assert progress["source"] == "rollup"
    assert progress["pct"] == 0


# ---------------------------------------------------------------------------
# Linking an existing goal as a subgoal (re-parenting, 2026-08-29)
# ---------------------------------------------------------------------------


def test_linking_existing_goal_reparents_it(brain):
    a = _mk("Goal A")
    b = _mk("Goal B")
    result = goals_service.update_goal(USER, b["id"], {"parent_id": a["id"]})
    assert result["parent_id"] == a["id"]
    assert goals_service.get_subgoals(USER, a["id"]) == [result]


def test_linking_existing_goal_can_move_it_from_one_parent_to_another(brain):
    a = _mk("Parent A")
    b = _mk("Parent B")
    child = _mk("Child", parent_id=a["id"])
    goals_service.update_goal(USER, child["id"], {"parent_id": b["id"]})
    assert goals_service.get_subgoals(USER, a["id"]) == []
    moved = goals_service.get_goal(USER, child["id"])
    assert moved["parent_id"] == b["id"]


# ---------------------------------------------------------------------------
# Tags (2026-08-29)
# ---------------------------------------------------------------------------


def test_create_goal_with_tags_registers_vocabulary(brain):
    from services import tags_service

    g = _mk("Tagged goal", tags=["urgent", "q3"])
    assert g["tags"] == ["urgent", "q3"]
    assert tags_service.get_tags(USER, "personal") == ["urgent", "q3"]


def test_update_goal_tags_registers_new_vocabulary_entries(brain):
    from services import tags_service

    g = _mk("Plain goal")
    goals_service.update_goal(USER, g["id"], {"tags": ["new-tag"]})
    assert "new-tag" in tags_service.get_tags(USER, "personal")
