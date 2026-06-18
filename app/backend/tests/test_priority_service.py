"""Tests for task scoring logic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.priority_service import score_task


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
    s_low  = score_task(_task("Job", "Low"),  ORDER, "2024-06-01")
    assert s_high > s_low


def test_overdue_adds_10_urgency():
    base    = score_task(_task("God", "High"),             ORDER, "2024-06-01")
    overdue = score_task(_task("God", "High", "2024-05-31"), ORDER, "2024-06-01")
    assert overdue - base == 10


def test_due_today_adds_5():
    base  = score_task(_task("God", "High"),             ORDER, "2024-06-01")
    today = score_task(_task("God", "High", "2024-06-01"), ORDER, "2024-06-01")
    assert today - base == 5


def test_due_within_week_adds_2():
    base = score_task(_task("God", "High"),             ORDER, "2024-06-01")
    soon = score_task(_task("God", "High", "2024-06-07"), ORDER, "2024-06-01")
    assert soon - base == 2


def test_unknown_category_gets_zero_score():
    # cat_weight=0 → 0 * pri_weight = 0; no urgency
    assert score_task(_task("Unknown", "High"), ORDER, "2024-06-01") == 0


def test_medium_priority_weight():
    # cat_weight=5, pri_weight=2 → 10
    assert score_task(_task("God", "Medium"), ORDER, "2024-06-01") == 10
