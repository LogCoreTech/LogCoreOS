"""APScheduler background jobs — recurring processor, digests, overdue alerts, custom suggestions."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from services.auth_service import get_user_by_name, today_for_user, cleanup_revoked_jtis
from services.file_service import brain_path, tasks_path, read_json
from services.recurring_service import process_all_users

logger = logging.getLogger("logcore.scheduler")
scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)


def _all_users() -> list[str]:
    users_dir = brain_path() / "USERS"
    return [
        d.name for d in users_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_")
        and tasks_path(d.name).exists()
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
            refresh_version_cache, get_update_status,
            get_auto_update_enabled, trigger_update,
        )
        refresh_version_cache()
        if not get_auto_update_enabled():
            return
        status = get_update_status()
        if status.get("update_available") and not status.get("update_pending") and not status.get("update_running"):
            logger.info("auto-update: new version %s available — queuing update", status.get("latest_version"))
            trigger_update()
    except Exception:
        logger.exception("update check failed")


def job_workflow_sync():
    try:
        from services.n8n_service import sync_business_workflows
        result = sync_business_workflows()
        if any(result.get(k) for k in ("created", "updated", "deleted", "errors")):
            logger.info("workflow sync: %s", result)
    except Exception:
        logger.exception("business workflow sync failed")


def _custom_job_id(user_name: str, suggestion_id: str) -> str:
    return f"custom__{user_name}__{suggestion_id}"


def _trigger_for_custom(suggestion: dict):
    """Build an APScheduler trigger from a custom suggestion's schedule fields."""
    hour = suggestion.get("hour", 9)
    schedule = suggestion.get("schedule", "daily")
    if schedule == "interval":
        days = suggestion.get("interval_days") or 1
        from datetime import datetime, timedelta
        import math
        now = datetime.now()
        # Start at the next occurrence of 'hour' today or tomorrow
        start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if start <= now:
            start += timedelta(days=1)
        return IntervalTrigger(days=days, start_date=start)
    if schedule == "weekly":
        dow = suggestion.get("day_of_week", "mon")
        return CronTrigger(day_of_week=dow, hour=hour, minute=0)
    # default: daily
    return CronTrigger(hour=hour, minute=0)


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
    from datetime import datetime as _dt, timedelta as _td
    scheduler.add_job(job_recurring_processor,  CronTrigger(hour=0, minute=1),                                              id="recurring")
    scheduler.add_job(job_morning_digest,        CronTrigger(hour=settings.morning_digest_hour, minute=0),                  id="morning")
    scheduler.add_job(job_overdue_check,         CronTrigger(hour=settings.overdue_check_hour, minute=0),                   id="overdue")
    scheduler.add_job(job_weekly_review,         CronTrigger(day_of_week="sun", hour=settings.overdue_check_hour, minute=0), id="weekly")
    scheduler.add_job(job_goal_drift,            CronTrigger(hour=settings.overdue_check_hour, minute=30),                  id="goal_drift")
    scheduler.add_job(job_cleanup_revoked_jtis,  CronTrigger(hour=3, minute=0),                                             id="jti_cleanup")
    # Workflow sync: 90s after boot (wait for n8n), then every 6 hours
    scheduler.add_job(job_workflow_sync,  "date",                  run_date=_dt.now() + _td(seconds=90), id="workflow_sync_boot")
    scheduler.add_job(job_workflow_sync,  IntervalTrigger(hours=6),                                        id="workflow_sync_periodic")
    scheduler.add_job(job_update_check,   CronTrigger(hour=12, minute=0),                                  id="update_check")
    scheduler.start()
    _load_custom_jobs()
    logger.info(
        "scheduler started — recurring@00:01, morning@%02d:00, overdue@%02d:00, weekly@Sun %02d:00, goal_drift@%02d:30 (%s)",
        settings.morning_digest_hour, settings.overdue_check_hour, settings.overdue_check_hour,
        settings.overdue_check_hour, settings.scheduler_timezone,
    )
