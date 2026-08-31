"""APScheduler background jobs — recurring processor, digests, overdue alerts, custom suggestions."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from services.auth_service import cleanup_revoked_jtis, get_user_by_name, today_for_user
from services.file_service import brain_path, read_json, tasks_path
from services.recurring_service import process_all_users

logger = logging.getLogger("logcore.scheduler")
scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)


def _cron(**kwargs) -> CronTrigger:
    """CronTrigger, defaulted to the scheduler's own configured timezone.

    APScheduler's BackgroundScheduler(timezone=...) constructor arg does NOT
    apply to a trigger object constructed and passed to add_job() directly —
    that auto-injection only happens on the "pass a trigger alias string +
    kwargs" call shape (see apscheduler.schedulers.base._create_trigger).
    Every CronTrigger/IntervalTrigger here was constructed the object-first
    way with no explicit timezone=, so each one silently resolved its own
    timezone via get_localzone() (the container's SYSTEM timezone, not
    SCHEDULER_TIMEZONE) at construction time — every scheduled job in this
    app was firing at the wrong wall-clock time whenever the container's
    system tz differs from SCHEDULER_TIMEZONE (the normal case: Docker base
    images default to UTC, this app's own default is America/Chicago).
    Route every trigger through here (or _interval below) instead of
    constructing CronTrigger/IntervalTrigger directly, so this can't
    regress the next time a job is added."""
    kwargs.setdefault("timezone", scheduler.timezone)
    return CronTrigger(**kwargs)


def _interval(**kwargs) -> IntervalTrigger:
    """IntervalTrigger, defaulted to the scheduler's own configured timezone — see _cron()."""
    kwargs.setdefault("timezone", scheduler.timezone)
    return IntervalTrigger(**kwargs)


def _all_users() -> list[str]:
    users_dir = brain_path() / "USERS"
    return [
        d.name
        for d in users_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_") and tasks_path(d.name).exists()
    ]


def _all_user_workspace_pairs() -> list[tuple[str, str]]:
    """Return (user_name, workspace) pairs for all users × their enabled workspaces."""
    pairs = []
    users_dir = brain_path() / "USERS"
    for d in users_dir.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        user_record = get_user_by_name(d.name) or {}
        workspaces = user_record.get("workspaces", ["personal"])
        for ws in workspaces:
            if ws == "personal" and tasks_path(d.name).exists():
                pairs.append((d.name, ws))
            elif ws == "business":
                pairs.append((d.name, ws))
    return pairs


def job_recurring_processor():
    try:
        results = process_all_users()
        logger.info("recurring processor: %s", results)
    except Exception:
        logger.exception("recurring processor failed")


def job_morning_digest():
    from services.suggestions_service import get_config, run_suggestion_sync

    for user, workspace in _all_user_workspace_pairs():
        try:
            cfg = get_config(user)
            if not cfg["daily_digest"].get("enabled", True):
                continue
            run_suggestion_sync(user, "daily_digest", workspace)
        except Exception:
            logger.exception("morning digest failed for %s/%s", user, workspace)


def job_overdue_check():
    from services.suggestions_service import get_config, run_suggestion_sync

    for user, workspace in _all_user_workspace_pairs():
        try:
            cfg = get_config(user)
            if not cfg["overdue_alert"].get("enabled", True):
                continue
            run_suggestion_sync(user, "overdue_alert", workspace)
        except Exception:
            logger.exception("overdue check failed for %s/%s", user, workspace)


def job_weekly_review():
    from services.suggestions_service import get_config, run_suggestion_sync

    for user, workspace in _all_user_workspace_pairs():
        try:
            cfg = get_config(user)
            if not cfg["weekly_review"].get("enabled", True):
                continue
            run_suggestion_sync(user, "weekly_review", workspace)
        except Exception:
            logger.exception("weekly review failed for %s/%s", user, workspace)


def job_goal_drift():
    from services.suggestions_service import get_config, run_suggestion_sync

    for user, workspace in _all_user_workspace_pairs():
        try:
            cfg = get_config(user)
            if not cfg["goal_drift"].get("enabled", True):
                continue
            run_suggestion_sync(user, "goal_drift", workspace)
        except Exception:
            logger.exception("goal drift check failed for %s/%s", user, workspace)


def job_goal_due_urgency():
    from services.suggestions_service import get_config, run_suggestion_sync

    for user, workspace in _all_user_workspace_pairs():
        try:
            cfg = get_config(user)
            if not cfg["goal_due_urgency"].get("enabled", True):
                continue
            run_suggestion_sync(user, "goal_due_urgency", workspace)
        except Exception:
            logger.exception("goal due-urgency check failed for %s/%s", user, workspace)


def job_goal_progress_snapshot():
    """Runs BEFORE job_goal_drift (see start()'s scheduling) so today's
    snapshot exists by the time drift compares against it. Also fires the
    completion-celebration notification for any goal that crossed from
    <100% to >=100% since the prior snapshot — see
    module_packages/goals/backend/service.py's snapshot_progress() docstring
    for why this is checked once daily here rather than on every write."""
    from module_packages.goals.backend import service as goals_service
    from services.suggestions_service import notify_user

    stores: list[tuple[str, str]] = list(_all_user_workspace_pairs())
    stores += [("_household", "personal"), ("_team", "personal")]

    for store_user, workspace in stores:
        try:
            user = {"name": store_user}
            newly_complete = goals_service.snapshot_progress(store_user, workspace, user)
            if store_user.startswith("_"):
                continue  # pool completions don't have one single person to notify
            for goal in newly_complete:
                notify_user(
                    store_user,
                    f"🎉 You hit 100% on \"{goal['title']}\"!",
                    "Nice work — that goal is complete.",
                    source="goal_complete",
                    action={"type": "open_goal", "goal_id": goal["id"]},
                    url="/goals",
                )
        except Exception:
            logger.exception("goal progress snapshot failed for %s/%s", store_user, workspace)


def job_custom_suggestion(user_name: str, suggestion: dict):
    from services.suggestions_service import run_suggestion_sync

    try:
        run_suggestion_sync(user_name, suggestion["id"])
    except Exception:
        logger.exception("custom suggestion %s failed for %s", suggestion.get("id"), user_name)


def job_cleanup_revoked_jtis():
    try:
        cleanup_revoked_jtis()
    except Exception:
        logger.exception("revoked JTI cleanup failed")


def job_update_check():
    """Daily: refresh GitHub version cache. Auto-trigger update if admin has enabled it."""
    try:
        from services.update_service import (
            get_auto_update_enabled,
            get_update_status,
            refresh_version_cache,
            trigger_update,
        )

        refresh_version_cache()
        # Catch-up announce: update.sh stamps installed_version.json AFTER the app
        # restarts, so the boot-time announce can read the old version and stay
        # silent. Re-checking here (and in the boot+180s one-shot) closes that gap.
        from services.whats_new_service import announce_if_updated

        announce_if_updated()
        if not get_auto_update_enabled():
            return
        status = get_update_status()
        if (
            status.get("update_available")
            and not status.get("update_pending")
            and not status.get("update_running")
        ):
            logger.info(
                "auto-update: new version %s available — queuing update",
                status.get("latest_version"),
            )
            trigger_update()
    except Exception:
        logger.exception("update check failed")


def job_whats_new_recheck():
    """Boot+180s: re-run the What's-New announce after update.sh has stamped the version."""
    try:
        from services.whats_new_service import announce_if_updated

        announce_if_updated()
    except Exception:
        logger.exception("whats-new recheck failed")


def job_workflow_sync():
    try:
        from services.n8n_service import sync_business_workflows

        result = sync_business_workflows()
        if any(result.get(k) for k in ("created", "updated", "deleted", "errors")):
            logger.info("workflow sync: %s", result)
    except Exception:
        logger.exception("business workflow sync failed")


def job_simplefin_sync():
    try:
        from services.simplefin_service import sync_all_users

        result = sync_all_users()
        if result.get("users"):
            logger.info("simplefin sync: %s", result)
    except Exception:
        logger.exception("simplefin sync failed")


def job_n8n_reconcile():
    """Boot reconcile: keep the bundled n8n running only when needed."""
    try:
        from services import n8n_service

        logger.info("n8n reconcile: %s", n8n_service.reconcile())
    except Exception:
        logger.exception("n8n reconcile failed")


def job_finance_nightly():
    """Missed-bill flags, budget alerts and balance-deviation checks."""
    try:
        from services.finance_planning_service import run_nightly

        run_nightly()
    except Exception:
        logger.exception("finance nightly failed")


def job_contacts_followups():
    """Notify owners of due CRM follow-ups (interactions + deals)."""
    try:
        from services.contacts_service import run_followup_reminders

        run_followup_reminders()
    except Exception:
        logger.exception("contacts follow-up sweep failed")


def job_channel_rotation_check():
    """Monthly per-user reminders to rotate the ntfy notification channel."""
    try:
        from services.suggestions_service import run_channel_rotation_reminders

        run_channel_rotation_reminders()
    except Exception:
        logger.exception("channel rotation reminder sweep failed")


def _custom_job_id(user_name: str, suggestion_id: str) -> str:
    return f"custom__{user_name}__{suggestion_id}"


def _trigger_for_custom(suggestion: dict):
    """Build an APScheduler trigger from a custom suggestion's schedule fields."""
    hour = suggestion.get("hour", 9)
    schedule = suggestion.get("schedule", "daily")
    if schedule == "interval":
        days = suggestion.get("interval_days") or 1
        from datetime import datetime, timedelta

        # Timezone-aware "now" in the scheduler's own configured timezone (not
        # naive/system-local — see _cron()'s docstring) so `hour` is correctly
        # interpreted as SCHEDULER_TIMEZONE wall-clock time, not container-local.
        now = datetime.now(scheduler.timezone)
        # Start at the next occurrence of 'hour' today or tomorrow
        start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if start <= now:
            start += timedelta(days=1)
        return _interval(days=days, start_date=start)
    if schedule == "weekly":
        dow = suggestion.get("day_of_week", "mon")
        return _cron(day_of_week=dow, hour=hour, minute=0)
    # default: daily
    return _cron(hour=hour, minute=0)


def add_custom_job(user_name: str, suggestion: dict) -> None:
    """Register a custom suggestion as a live APScheduler job."""
    job_id = _custom_job_id(user_name, suggestion["id"])
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    trigger = _trigger_for_custom(suggestion)
    scheduler.add_job(
        job_custom_suggestion,
        trigger,
        args=[user_name, suggestion],
        id=job_id,
        replace_existing=True,
    )
    logger.info("registered custom job %s for %s", job_id, user_name)


def remove_custom_job(user_name: str, suggestion_id: str) -> None:
    """Unregister a custom suggestion job if it exists."""
    job_id = _custom_job_id(user_name, suggestion_id)
    job = scheduler.get_job(job_id)
    if job:
        scheduler.remove_job(job_id)
        logger.info("removed custom job %s", job_id)


def _load_custom_jobs() -> None:
    """On startup, register all existing custom suggestions across all users."""
    from services.suggestions_service import get_config

    for user in _all_users():
        try:
            cfg = get_config(user)
            for s in cfg.get("custom", []):
                if s.get("enabled", True):
                    add_custom_job(user, s)
        except Exception:
            logger.exception("failed to load custom jobs for %s", user)


def start():
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    # Boot-relative "date" jobs below all anchor on _dt.now(scheduler.timezone) —
    # NOT naive _dt.now(). Real bug found 2026-08-31 (owner report: boot-time jobs
    # never actually fired): a "date" trigger passed as the string alias "date" gets
    # scheduler.timezone auto-injected by APScheduler's own _create_trigger() (see
    # _cron()'s docstring above for the same mechanism). If run_date is a NAIVE
    # datetime built from a container whose system clock reads UTC wall-clock values
    # (the normal case — Docker images default to UTC), attaching the "America/
    # Chicago" label to those UTC-valued numbers doesn't convert them, it just
    # mislabels them — producing a run_date several hours further in the future than
    # intended (confirmed directly: a job meant to fire in 3 seconds computed a
    # 18000-second, i.e. 5-hour, wait instead). datetime.now(scheduler.timezone)
    # computes a genuinely correct current moment in that zone instead.
    scheduler.add_job(job_recurring_processor, _cron(hour=0, minute=1), id="recurring")
    # Also run once shortly after boot — the nightly cron above only self-heals a
    # stale/overdue recurring task once per local day, so a task that went stale
    # while the app was down (or running old/buggy scheduling code) would otherwise
    # sit wrong for up to 24h after a restart before the next midnight run touches
    # it. process_user() is idempotent (a task with nothing stale is a no-op), so
    # this can't double-process anything even if it lands right next to the nightly
    # run. Same boot-then-periodic shape as workflow_sync/simplefin/n8n_reconcile below.
    scheduler.add_job(
        job_recurring_processor,
        "date",
        run_date=_dt.now(scheduler.timezone) + _td(seconds=15),
        id="recurring_boot",
    )
    scheduler.add_job(
        job_morning_digest, _cron(hour=settings.morning_digest_hour, minute=0), id="morning"
    )
    scheduler.add_job(
        job_overdue_check, _cron(hour=settings.overdue_check_hour, minute=0), id="overdue"
    )
    scheduler.add_job(
        job_weekly_review,
        _cron(day_of_week="sun", hour=settings.overdue_check_hour, minute=0),
        id="weekly",
    )
    scheduler.add_job(
        job_goal_progress_snapshot,
        _cron(hour=settings.overdue_check_hour, minute=15),
        id="goal_progress_snapshot",
    )
    scheduler.add_job(
        job_goal_drift, _cron(hour=settings.overdue_check_hour, minute=30), id="goal_drift"
    )
    scheduler.add_job(
        job_goal_due_urgency,
        _cron(hour=settings.overdue_check_hour, minute=35),
        id="goal_due_urgency",
    )
    scheduler.add_job(job_cleanup_revoked_jtis, _cron(hour=3, minute=0), id="jti_cleanup")
    # Workflow sync: 90s after boot (wait for n8n), then every 6 hours
    scheduler.add_job(
        job_workflow_sync,
        "date",
        run_date=_dt.now(scheduler.timezone) + _td(seconds=90),
        id="workflow_sync_boot",
    )
    scheduler.add_job(job_workflow_sync, _interval(hours=6), id="workflow_sync_periodic")
    scheduler.add_job(job_update_check, _cron(hour=12, minute=0), id="update_check")
    # SimpleFIN bank sync: 2 min after boot, then every 12h (bridge data refreshes ~daily)
    scheduler.add_job(
        job_simplefin_sync,
        "date",
        run_date=_dt.now(scheduler.timezone) + _td(seconds=120),
        id="simplefin_boot",
    )
    scheduler.add_job(job_simplefin_sync, _interval(hours=12), id="simplefin_periodic")
    scheduler.add_job(job_finance_nightly, _cron(hour=7, minute=30), id="finance_nightly")
    scheduler.add_job(job_contacts_followups, _cron(hour=8, minute=0), id="contacts_followups")
    scheduler.add_job(job_channel_rotation_check, _cron(hour=9, minute=30), id="channel_rotation")
    scheduler.add_job(
        job_n8n_reconcile,
        "date",
        run_date=_dt.now(scheduler.timezone) + _td(seconds=100),
        id="n8n_reconcile_boot",
    )
    # What's-New catch-up: update.sh stamps installed_version.json only after the
    # restarted app passes its health check, so the in-lifespan announce misses
    # fresh updates. One-shot re-check well after the stamp has landed.
    scheduler.add_job(
        job_whats_new_recheck,
        "date",
        run_date=_dt.now(scheduler.timezone) + _td(seconds=180),
        id="whats_new_boot",
    )
    scheduler.start()
    _load_custom_jobs()
    logger.info(
        "scheduler started — recurring@00:01, morning@%02d:00, overdue@%02d:00, weekly@Sun %02d:00, "
        "goal_progress_snapshot@%02d:15, goal_drift@%02d:30, goal_due_urgency@%02d:35 (%s)",
        settings.morning_digest_hour,
        settings.overdue_check_hour,
        settings.overdue_check_hour,
        settings.overdue_check_hour,
        settings.overdue_check_hour,
        settings.overdue_check_hour,
        settings.scheduler_timezone,
    )
