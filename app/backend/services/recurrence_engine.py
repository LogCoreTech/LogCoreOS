"""Next-occurrence math for recurring tasks — stdlib only, no external rrule dependency.

Structured rule shape (mirrors routers/_task_models.py's RecurrenceRule):
{
  "freq": "daily" | "weekly" | "monthly" | "yearly",
  "interval": 1,
  "weekdays": ["MO","WE","FR"],                   # weekly only
  "month_day": 15,                                 # monthly/yearly "day N" mode; -1 = last day
  "month_week": {"ordinal": 2, "weekday": "TU"},   # monthly/yearly "Nth weekday" mode
  "month": 3,                                       # yearly only
}

dateutil's rrule was deliberately not used here: its bymonthday SKIPS months where that
day doesn't exist (e.g. day 31 skips February) instead of clamping, which would silently
change behavior for existing tasks migrated from the old daily/weekly/monthly string
model. This module clamps, matching the previous _next_due()'s behavior exactly for the
day-of-month case, and needs no new dependency for the weekday/ordinal cases either.
"""

import calendar
from datetime import date, timedelta

_WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]  # date.weekday(): 0=Mon..6=Sun


def _weekday_index(code: str) -> int:
    return _WEEKDAY_CODES.index(code)


def _clamped_month_day(year: int, month: int, month_day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    day = last_day if month_day == -1 else min(month_day, last_day)
    return date(year, month, day)


def _add_months(year: int, month: int, months: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + months
    return total // 12, total % 12 + 1


def _nth_weekday_of_month(year: int, month: int, weekday_code: str, ordinal: int) -> date:
    target_wd = _weekday_index(weekday_code)
    last_day = calendar.monthrange(year, month)[1]
    matches = [d for d in range(1, last_day + 1) if date(year, month, d).weekday() == target_wd]
    if ordinal == -1:
        return date(year, month, matches[-1])
    if ordinal > len(matches):
        raise ValueError(f"{year}-{month:02d} has no {ordinal}th {weekday_code}")
    return date(year, month, matches[ordinal - 1])


def next_occurrence(current_due: str, rule: dict) -> str:
    """Given a task's current due date and its recurrence rule, return the next due date.

    `current_due` is assumed to already be a valid occurrence of the rule (this is how
    every caller in recurring_service.py uses it — chaining occurrence to occurrence keeps
    interval-N cadences correctly phased without needing to store a separate series-start
    date). The one exception is the nightly "broken streak" recovery path, which advances
    from *today* instead of the stale due date on purpose (see recurring_service.py) — for
    an interval>1 pattern this can shift which week/month is "active" after a long miss;
    that's an accepted trade-off for always recovering promptly, not a bug to chase here.
    """
    freq = rule.get("freq")
    interval = rule.get("interval") or 1
    d = date.fromisoformat(current_due)

    if freq == "daily":
        return (d + timedelta(days=interval)).isoformat()

    if freq == "weekly":
        weekdays = rule.get("weekdays") or []
        if not weekdays:
            raise ValueError("weekly recurrence requires non-empty weekdays")
        targets = sorted(_weekday_index(w) for w in weekdays)
        for wd in targets:
            if wd > d.weekday():
                return (d + timedelta(days=wd - d.weekday())).isoformat()
        this_monday = d - timedelta(days=d.weekday())
        next_monday = this_monday + timedelta(weeks=interval)
        return (next_monday + timedelta(days=targets[0])).isoformat()

    if freq == "monthly":
        year, month = _add_months(d.year, d.month, interval)
    elif freq == "yearly":
        month = rule.get("month")
        if month is None:
            raise ValueError("yearly recurrence requires month")
        year = d.year + interval
    else:
        raise ValueError(f"unknown recurrence freq: {freq!r}")

    month_day = rule.get("month_day")
    month_week = rule.get("month_week")
    if month_day is not None:
        return _clamped_month_day(year, month, month_day).isoformat()
    if month_week is not None:
        return _nth_weekday_of_month(
            year, month, month_week["weekday"], month_week["ordinal"]
        ).isoformat()
    raise ValueError(f"{freq} recurrence requires month_day or month_week")


def first_occurrence_on_or_after(anchor: str, rule: dict) -> str:
    """The earliest valid occurrence of `rule` on or after `anchor` — gives a freshly
    created recurring task (or one that's somehow missing a due_date entirely) a real
    starting date, without needing a stored series-start to reference. Unlike
    next_occurrence(), `interval` does not affect this first pick: "every 2 weeks on
    Wed" still starts on the very next Wednesday, not one skipped — interval only
    governs the gap between occurrences AFTER this one, once next_occurrence() takes
    over."""
    freq = rule.get("freq")
    d = date.fromisoformat(anchor)

    if freq == "daily":
        return anchor  # every day matches; the anchor itself is always valid

    if freq == "weekly":
        weekdays = rule.get("weekdays") or []
        if not weekdays:
            raise ValueError("weekly recurrence requires non-empty weekdays")
        targets = sorted(_weekday_index(w) for w in weekdays)
        for wd in targets:
            if wd >= d.weekday():
                return (d + timedelta(days=wd - d.weekday())).isoformat()
        this_monday = d - timedelta(days=d.weekday())
        return (this_monday + timedelta(weeks=1, days=targets[0])).isoformat()

    if freq in ("monthly", "yearly"):
        month_day = rule.get("month_day")
        month_week = rule.get("month_week")

        def _candidate(y: int, m: int) -> date:
            if month_day is not None:
                return _clamped_month_day(y, m, month_day)
            if month_week is not None:
                return _nth_weekday_of_month(y, m, month_week["weekday"], month_week["ordinal"])
            raise ValueError(f"{freq} recurrence requires month_day or month_week")

        if freq == "yearly":
            month = rule.get("month")
            if month is None:
                raise ValueError("yearly recurrence requires month")
            year = d.year
        else:
            year, month = d.year, d.month

        candidate = _candidate(year, month)
        if candidate >= d:
            return candidate.isoformat()

        year, month = _add_months(year, month, 1) if freq == "monthly" else (year + 1, month)
        return _candidate(year, month).isoformat()

    raise ValueError(f"unknown recurrence freq: {freq!r}")


def legacy_recurrence_to_rule(recurrence: str, due_date: str | None) -> dict:
    """Convert a pre-2026-08-30 plain recurrence string into the structured shape,
    deriving the weekday/day-of-month from the task's own due_date so its actual
    behavior doesn't change on migration. Falls back to today when due_date is missing.
    """
    anchor = date.fromisoformat(due_date) if due_date else date.today()

    if recurrence == "weekly":
        return {"freq": "weekly", "interval": 1, "weekdays": [_WEEKDAY_CODES[anchor.weekday()]]}
    if recurrence == "monthly":
        return {"freq": "monthly", "interval": 1, "month_day": anchor.day}
    # "daily" and any unrecognized legacy value fell back to daily behavior in the old
    # _next_due() (`return (d + timedelta(days=1)).isoformat()` as its final line).
    return {"freq": "daily", "interval": 1}
