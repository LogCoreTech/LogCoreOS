"""Tests for scheduler.py's trigger-timezone handling.

Real bug (found 2026-08-30, owner report: "the morning 3 pillar notification
just fired at 11 pm when it's supposed to fire at 4 AM"): APScheduler's
BackgroundScheduler(timezone=...) constructor arg does NOT apply to a trigger
object constructed and passed to add_job() directly — every CronTrigger/
IntervalTrigger in this file was built with no explicit timezone=, so each
one silently resolved its own timezone via get_localzone() (the container's
SYSTEM timezone) instead of settings.scheduler_timezone. Every scheduled job
in the app — not just custom suggestions — was affected whenever the
container's system tz differs from SCHEDULER_TIMEZONE (the normal case:
Docker images default to UTC; this app's own default is America/Chicago,
UTC-5/UTC-6 — a 4 AM local target firing as 4 AM UTC lands at 11 PM/10 PM
local the prior day, exactly matching the reported symptom).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apscheduler.util import astimezone

import scheduler as scheduler_module
from scheduler import _cron, _interval, _trigger_for_custom, scheduler


def test_scheduler_timezone_is_not_the_system_default():
    # Sanity check on the fixture/config itself, not the fix: confirms the
    # scheduler really is configured to a specific zone (not just whatever
    # get_localzone() would already return), so the tests below are actually
    # exercising something meaningful.
    from config import settings

    assert scheduler.timezone == astimezone(settings.scheduler_timezone)


def test_cron_helper_defaults_to_scheduler_timezone():
    trigger = _cron(hour=4, minute=0)
    assert trigger.timezone == scheduler.timezone


def test_interval_helper_defaults_to_scheduler_timezone():
    trigger = _interval(hours=6)
    assert trigger.timezone == scheduler.timezone


def test_cron_helper_explicit_timezone_not_overridden():
    other = astimezone("UTC")
    trigger = _cron(hour=4, minute=0, timezone=other)
    assert trigger.timezone == other


def test_trigger_for_custom_daily_uses_scheduler_timezone():
    trigger = _trigger_for_custom({"schedule": "daily", "hour": 4})
    assert trigger.timezone == scheduler.timezone


def test_trigger_for_custom_weekly_uses_scheduler_timezone():
    trigger = _trigger_for_custom({"schedule": "weekly", "hour": 4, "day_of_week": "mon"})
    assert trigger.timezone == scheduler.timezone


def test_trigger_for_custom_interval_uses_scheduler_timezone():
    trigger = _trigger_for_custom({"schedule": "interval", "hour": 4, "interval_days": 2})
    assert trigger.timezone == scheduler.timezone


def test_trigger_for_custom_interval_start_date_is_the_requested_wall_clock_hour():
    """The actual reported bug: a custom suggestion with hour=4 must resolve to
    4 AM in the scheduler's configured timezone, not 4 AM in the container's
    system timezone (whatever that happens to be)."""
    trigger = _trigger_for_custom({"schedule": "interval", "hour": 4, "interval_days": 1})
    assert trigger.start_date.tzinfo is not None
    local_start = trigger.start_date.astimezone(scheduler.timezone)
    assert local_start.hour == 4
    assert local_start.minute == 0


def test_every_start_job_trigger_uses_scheduler_timezone(monkeypatch):
    """Registers every job start() would register (minus scheduler.start()
    itself, which would spin up a live background thread) and asserts each
    one's trigger carries the scheduler's own timezone — the regression
    guard for the bug class, not just the one custom-suggestion code path."""
    registered = []

    def _spy_add_job(func, trigger=None, **kwargs):
        registered.append((kwargs.get("id"), trigger))
        return None

    monkeypatch.setattr(scheduler_module.scheduler, "add_job", _spy_add_job)
    monkeypatch.setattr(scheduler_module.scheduler, "start", lambda: None)
    monkeypatch.setattr(scheduler_module, "_load_custom_jobs", lambda: None)

    scheduler_module.start()

    cron_or_interval = [
        (job_id, trig)
        for job_id, trig in registered
        if hasattr(trig, "timezone")  # excludes the 4 boot-time "date" triggers
    ]
    assert cron_or_interval, "expected at least one cron/interval job to be registered"
    for job_id, trig in cron_or_interval:
        assert trig.timezone == scheduler.timezone, f"job {job_id!r} has the wrong timezone"
