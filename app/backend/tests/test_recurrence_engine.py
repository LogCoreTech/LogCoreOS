"""Tests for services/recurrence_engine.py — next-occurrence math and the
legacy string -> structured rule converter used by the m032 migration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services.recurrence_engine import (
    first_occurrence_on_or_after,
    legacy_recurrence_to_rule,
    next_occurrence,
)

# ---------------------------------------------------------------------------
# daily
# ---------------------------------------------------------------------------


def test_daily():
    assert next_occurrence("2024-01-31", {"freq": "daily", "interval": 1}) == "2024-02-01"


def test_daily_interval():
    assert next_occurrence("2024-01-31", {"freq": "daily", "interval": 3}) == "2024-02-03"


# ---------------------------------------------------------------------------
# weekly
# ---------------------------------------------------------------------------


def test_weekly_single_weekday():
    # 2024-01-01 is a Monday
    assert (
        next_occurrence("2024-01-01", {"freq": "weekly", "interval": 1, "weekdays": ["MO"]})
        == "2024-01-08"
    )


def test_weekly_multiple_weekdays_same_week():
    # 2024-01-01 (Mon) -> next matching weekday this week is Wed
    assert (
        next_occurrence(
            "2024-01-01", {"freq": "weekly", "interval": 1, "weekdays": ["MO", "WE", "FR"]}
        )
        == "2024-01-03"
    )


def test_weekly_multiple_weekdays_wraps_to_next_week():
    # 2024-01-05 (Fri) -> no later match this week -> next week's Monday
    assert (
        next_occurrence(
            "2024-01-05", {"freq": "weekly", "interval": 1, "weekdays": ["MO", "WE", "FR"]}
        )
        == "2024-01-08"
    )


def test_weekly_interval_two_wraps_two_weeks():
    # 2024-01-05 (Fri, last matching day of its active week) -> skip a week -> Jan 15 (Mon)
    assert (
        next_occurrence(
            "2024-01-05", {"freq": "weekly", "interval": 2, "weekdays": ["MO", "WE", "FR"]}
        )
        == "2024-01-15"
    )


def test_weekly_interval_two_stays_within_active_week():
    # 2024-01-01 (Mon) -> Wed is still later in the SAME active week, interval doesn't apply yet
    assert (
        next_occurrence(
            "2024-01-01", {"freq": "weekly", "interval": 2, "weekdays": ["MO", "WE", "FR"]}
        )
        == "2024-01-03"
    )


def test_weekly_empty_weekdays_raises():
    with pytest.raises(ValueError):
        next_occurrence("2024-01-01", {"freq": "weekly", "interval": 1, "weekdays": []})


# ---------------------------------------------------------------------------
# monthly — day-of-month mode (clamped, ported from the old _next_due tests)
# ---------------------------------------------------------------------------


def test_monthly_day_normal():
    assert (
        next_occurrence("2024-01-15", {"freq": "monthly", "interval": 1, "month_day": 15})
        == "2024-02-15"
    )


def test_monthly_day_end_of_month_clamped():
    # Jan 31 -> Feb 29 in leap year 2024
    assert (
        next_occurrence("2024-01-31", {"freq": "monthly", "interval": 1, "month_day": 31})
        == "2024-02-29"
    )


def test_monthly_day_leap_year_feb_to_mar():
    assert (
        next_occurrence("2024-02-29", {"freq": "monthly", "interval": 1, "month_day": 31})
        == "2024-03-31"
    )


def test_monthly_day_clamp_non_leap_year():
    # 2025 is NOT a leap year
    assert (
        next_occurrence("2025-01-31", {"freq": "monthly", "interval": 1, "month_day": 31})
        == "2025-02-28"
    )


def test_monthly_day_century_year_not_leap():
    # 1900 was NOT a leap year (divisible by 100 but not 400)
    assert (
        next_occurrence("1900-01-31", {"freq": "monthly", "interval": 1, "month_day": 31})
        == "1900-02-28"
    )


def test_monthly_day_400_year_is_leap():
    # 2000 WAS a leap year (divisible by 400)
    assert (
        next_occurrence("2000-01-31", {"freq": "monthly", "interval": 1, "month_day": 31})
        == "2000-02-29"
    )


def test_monthly_day_year_rollover():
    assert (
        next_occurrence("2024-12-15", {"freq": "monthly", "interval": 1, "month_day": 15})
        == "2025-01-15"
    )


def test_monthly_day_year_rollover_end_of_month():
    assert (
        next_occurrence("2024-12-31", {"freq": "monthly", "interval": 1, "month_day": 31})
        == "2025-01-31"
    )


def test_monthly_day_last_day_mode():
    assert (
        next_occurrence("2024-01-31", {"freq": "monthly", "interval": 1, "month_day": -1})
        == "2024-02-29"
    )


def test_monthly_day_interval_two():
    assert (
        next_occurrence("2024-01-15", {"freq": "monthly", "interval": 2, "month_day": 15})
        == "2024-03-15"
    )


# ---------------------------------------------------------------------------
# monthly — Nth-weekday mode
# ---------------------------------------------------------------------------


def test_monthly_2nd_tuesday():
    # 2024-01-09 is the 2nd Tuesday of January 2024
    assert (
        next_occurrence(
            "2024-01-09",
            {"freq": "monthly", "interval": 1, "month_week": {"ordinal": 2, "weekday": "TU"}},
        )
        == "2024-02-13"
    )  # 2nd Tuesday of Feb 2024


def test_monthly_last_weekday():
    assert (
        next_occurrence(
            "2024-01-30",  # last Tuesday of Jan 2024
            {"freq": "monthly", "interval": 1, "month_week": {"ordinal": -1, "weekday": "TU"}},
        )
        == "2024-02-27"
    )  # last Tuesday of Feb 2024


def test_monthly_ordinal_that_doesnt_exist_raises():
    # Only reachable with an out-of-range ordinal that bypasses the API's own
    # Literal[1,2,3,4,-1] constraint (e.g. a malformed AI tool call) — every
    # real month has at least 4 occurrences of every weekday, but never 5 for
    # a weekday that starts late in the month. Feb 2024's Tuesdays are
    # 6/13/20/27 — no 5th.
    with pytest.raises(ValueError):
        next_occurrence(
            "2024-01-01",
            {"freq": "monthly", "interval": 1, "month_week": {"ordinal": 5, "weekday": "TU"}},
        )


# ---------------------------------------------------------------------------
# yearly
# ---------------------------------------------------------------------------


def test_yearly_day_mode():
    assert (
        next_occurrence(
            "2024-03-15", {"freq": "yearly", "interval": 1, "month": 3, "month_day": 15}
        )
        == "2025-03-15"
    )


def test_yearly_day_mode_interval_two():
    assert (
        next_occurrence(
            "2024-03-15", {"freq": "yearly", "interval": 2, "month": 3, "month_day": 15}
        )
        == "2026-03-15"
    )


def test_yearly_week_mode():
    # 2nd Tuesday of March 2024 -> 2nd Tuesday of March 2025
    assert (
        next_occurrence(
            "2024-03-12",
            {
                "freq": "yearly",
                "interval": 1,
                "month": 3,
                "month_week": {"ordinal": 2, "weekday": "TU"},
            },
        )
        == "2025-03-11"
    )


def test_yearly_missing_month_raises():
    with pytest.raises(ValueError):
        next_occurrence("2024-03-15", {"freq": "yearly", "interval": 1, "month_day": 15})


# ---------------------------------------------------------------------------
# invalid shapes
# ---------------------------------------------------------------------------


def test_unknown_freq_raises():
    with pytest.raises(ValueError):
        next_occurrence("2024-06-01", {"freq": "unknown"})


def test_monthly_missing_both_day_and_week_raises():
    with pytest.raises(ValueError):
        next_occurrence("2024-06-01", {"freq": "monthly", "interval": 1})


# ---------------------------------------------------------------------------
# legacy_recurrence_to_rule — the m032 migration's conversion mapping
# ---------------------------------------------------------------------------


def test_legacy_daily():
    assert legacy_recurrence_to_rule("daily", "2024-01-15") == {"freq": "daily", "interval": 1}


def test_legacy_weekly_derives_weekday_from_due_date():
    # 2024-01-03 is a Wednesday
    assert legacy_recurrence_to_rule("weekly", "2024-01-03") == {
        "freq": "weekly",
        "interval": 1,
        "weekdays": ["WE"],
    }


def test_legacy_monthly_derives_day_from_due_date():
    assert legacy_recurrence_to_rule("monthly", "2024-01-31") == {
        "freq": "monthly",
        "interval": 1,
        "month_day": 31,
    }


def test_legacy_unknown_falls_back_to_daily():
    assert legacy_recurrence_to_rule("unknown", "2024-01-15") == {"freq": "daily", "interval": 1}


def test_legacy_missing_due_date_falls_back_to_today():
    # Just confirms it doesn't raise and produces a well-shaped rule.
    rule = legacy_recurrence_to_rule("weekly", None)
    assert rule["freq"] == "weekly"
    assert len(rule["weekdays"]) == 1


# ---------------------------------------------------------------------------
# first_occurrence_on_or_after — the initial due_date for a brand-new
# recurring task (or one that's missing due_date entirely and needs healing)
# ---------------------------------------------------------------------------


def test_first_occurrence_daily_is_the_anchor_itself():
    assert (
        first_occurrence_on_or_after("2024-06-01", {"freq": "daily", "interval": 1}) == "2024-06-01"
    )


def test_first_occurrence_weekly_anchor_matches_a_target_weekday():
    # 2024-01-01 is a Monday, in the target set — starts today, not next week
    assert (
        first_occurrence_on_or_after(
            "2024-01-01", {"freq": "weekly", "interval": 1, "weekdays": ["MO", "WE", "FR"]}
        )
        == "2024-01-01"
    )


def test_first_occurrence_weekly_anchor_before_a_later_target_this_week():
    # 2024-01-01 is a Monday; target is Wednesday, still ahead this week
    assert (
        first_occurrence_on_or_after(
            "2024-01-01", {"freq": "weekly", "interval": 1, "weekdays": ["WE"]}
        )
        == "2024-01-03"
    )


def test_first_occurrence_weekly_anchor_after_every_target_this_week():
    # 2024-01-06 is a Saturday; targets are Mon/Wed/Fri, all already past this week
    assert (
        first_occurrence_on_or_after(
            "2024-01-06", {"freq": "weekly", "interval": 1, "weekdays": ["MO", "WE", "FR"]}
        )
        == "2024-01-08"
    )


def test_first_occurrence_weekly_interval_does_not_affect_the_first_pick():
    # Even with interval=2, the FIRST occurrence is still the very next matching
    # weekday — interval only governs the gap after that.
    assert (
        first_occurrence_on_or_after(
            "2024-01-06", {"freq": "weekly", "interval": 2, "weekdays": ["MO", "WE", "FR"]}
        )
        == "2024-01-08"
    )


def test_first_occurrence_monthly_day_still_ahead_this_month():
    assert (
        first_occurrence_on_or_after(
            "2024-01-10", {"freq": "monthly", "interval": 1, "month_day": 15}
        )
        == "2024-01-15"
    )


def test_first_occurrence_monthly_day_already_passed_this_month():
    assert (
        first_occurrence_on_or_after(
            "2024-01-20", {"freq": "monthly", "interval": 1, "month_day": 15}
        )
        == "2024-02-15"
    )


def test_first_occurrence_monthly_day_exactly_on_anchor():
    assert (
        first_occurrence_on_or_after(
            "2024-01-15", {"freq": "monthly", "interval": 1, "month_day": 15}
        )
        == "2024-01-15"
    )


def test_first_occurrence_monthly_last_day():
    assert (
        first_occurrence_on_or_after(
            "2024-02-10", {"freq": "monthly", "interval": 1, "month_day": -1}
        )
        == "2024-02-29"
    )


def test_first_occurrence_monthly_nth_weekday_still_ahead():
    # 2024-01-09 is the 2nd Tuesday of January 2024
    assert (
        first_occurrence_on_or_after(
            "2024-01-01",
            {"freq": "monthly", "interval": 1, "month_week": {"ordinal": 2, "weekday": "TU"}},
        )
        == "2024-01-09"
    )


def test_first_occurrence_monthly_nth_weekday_already_passed():
    assert (
        first_occurrence_on_or_after(
            "2024-01-15",
            {"freq": "monthly", "interval": 1, "month_week": {"ordinal": 2, "weekday": "TU"}},
        )
        == "2024-02-13"
    )


def test_first_occurrence_yearly_month_still_ahead_this_year():
    assert (
        first_occurrence_on_or_after(
            "2024-01-01", {"freq": "yearly", "interval": 1, "month": 3, "month_day": 15}
        )
        == "2024-03-15"
    )


def test_first_occurrence_yearly_month_already_passed_this_year():
    assert (
        first_occurrence_on_or_after(
            "2024-04-01", {"freq": "yearly", "interval": 1, "month": 3, "month_day": 15}
        )
        == "2025-03-15"
    )


def test_first_occurrence_yearly_same_month_day_already_passed():
    assert (
        first_occurrence_on_or_after(
            "2024-03-20", {"freq": "yearly", "interval": 1, "month": 3, "month_day": 15}
        )
        == "2025-03-15"
    )


def test_first_occurrence_yearly_missing_month_raises():
    with pytest.raises(ValueError):
        first_occurrence_on_or_after(
            "2024-01-01", {"freq": "yearly", "interval": 1, "month_day": 15}
        )
