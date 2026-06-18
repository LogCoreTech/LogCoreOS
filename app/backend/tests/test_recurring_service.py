"""Tests for recurring task date arithmetic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.recurring_service import _next_due


def test_daily():
    assert _next_due("2024-01-31", "daily") == "2024-02-01"


def test_weekly():
    assert _next_due("2024-01-01", "weekly") == "2024-01-08"


def test_monthly_normal():
    assert _next_due("2024-01-15", "monthly") == "2024-02-15"


def test_monthly_end_of_month_clamped():
    # Jan 31 → Feb 29 in leap year 2024
    assert _next_due("2024-01-31", "monthly") == "2024-02-29"


def test_monthly_leap_year_feb_to_mar():
    # Feb 29 in leap year → Mar 29
    assert _next_due("2024-02-29", "monthly") == "2024-03-29"


def test_monthly_clamp_non_leap_year():
    # Jan 31, 2025 → Feb 28 (2025 is NOT a leap year)
    assert _next_due("2025-01-31", "monthly") == "2025-02-28"


def test_monthly_century_year_not_leap():
    # 1900 was NOT a leap year (divisible by 100 but not 400)
    assert _next_due("1900-01-31", "monthly") == "1900-02-28"


def test_monthly_400_year_is_leap():
    # 2000 WAS a leap year (divisible by 400)
    assert _next_due("2000-01-31", "monthly") == "2000-02-29"


def test_monthly_year_rollover():
    assert _next_due("2024-12-15", "monthly") == "2025-01-15"


def test_monthly_year_rollover_end_of_month():
    # Dec 31 → Jan 31
    assert _next_due("2024-12-31", "monthly") == "2025-01-31"


def test_unknown_recurrence_falls_back_to_daily():
    assert _next_due("2024-06-01", "unknown") == "2024-06-02"
