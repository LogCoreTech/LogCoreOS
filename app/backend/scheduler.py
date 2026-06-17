"""APScheduler background jobs — recurring processor, digests, overdue alerts."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from services.auth_service import get_user_by_name, today_for_user
from services.file_service import brain_path, tasks_path, read_json
from services.priority_service import get_top3
from services.recurring_service import process_all_users
from services.notification_service import send

logger = logging.getLogger("logcore.scheduler")
scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)


def _all_users() -> list[str]:
    users_dir = brain_path() / "USERS"
    return [
        d.name for d in users_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_")
        and tasks_path(d.name).exists()
    ]


def _ntfy_channel(user_name: str) -> str:
    """Use the per-user random channel from auth.json; fall back to name-based if missing."""
    user = get_user_by_name(user_name)
    if user and user.get("notification_channel"):
        return user["notification_channel"]
    return f"logcore-{user_name.lower().replace(' ', '-')}"


def job_recurring_processor():
    try:
        results = process_all_users()
        logger.info("recurring processor: %s", results)
    except Exception:
        logger.exception("recurring processor failed")


def job_morning_digest():
    for user in _all_users():
        try:
            today = today_for_user(user)
            top3 = get_top3(user)
            if not top3:
                continue
            date_str = f"{today.strftime('%A, %B')} {today.day}"
            lines = "\n".join(
                f"{i+1}. [{t['category']}] {t['title']}" for i, t in enumerate(top3)
            )
            send(
                channel=_ntfy_channel(user),
                title=f"Good morning, {user.split()[0]}! — {date_str}",
                message=f"Your top 3 today:\n\n{lines}",
                priority="default",
            )
        except Exception:
            logger.exception("morning digest failed for %s", user)


def job_overdue_check():
    for user in _all_users():
        try:
            today = today_for_user(user).isoformat()
            data = read_json(tasks_path(user), default={"tasks": []})
            overdue = [
                t for t in data.get("tasks", [])
                if t.get("status") == "pending"
                and t.get("due_date")
                and t["due_date"] < today
            ]
            if not overdue:
                continue
            lines = "\n".join(
                f"• [{t['category']}] {t['title']} (due {t['due_date']})"
                for t in overdue
            )
            send(
                channel=_ntfy_channel(user),
                title=f"{len(overdue)} overdue task{'s' if len(overdue) > 1 else ''}",
                message=lines,
                priority="high",
            )
        except Exception:
            logger.exception("overdue check failed for %s", user)


def job_weekly_review():
    for user in _all_users():
        try:
            from datetime import timedelta
            week_ago = (today_for_user(user) - timedelta(days=7)).isoformat()
            from services.file_service import history_path
            history_file = history_path(user)
            if not history_file.exists():
                continue
            history = read_json(history_file, default={"tasks": []}).get("tasks", [])
            this_week = [t for t in history if (t.get("completed_at") or "") >= week_ago]
            if not this_week:
                continue
            by_cat: dict[str, int] = {}
            for t in this_week:
                by_cat[t["category"]] = by_cat.get(t["category"], 0) + 1
            lines = "\n".join(
                f"• {cat}: {count} task{'s' if count > 1 else ''}"
                for cat, count in sorted(by_cat.items(), key=lambda x: -x[1])
            )
            send(
                channel=_ntfy_channel(user),
                title=f"Weekly review — {len(this_week)} tasks completed",
                message=f"Great week, {user.split()[0]}!\n\n{lines}",
                priority="default",
            )
        except Exception:
            logger.exception("weekly review failed for %s", user)


def start():
    scheduler.add_job(job_recurring_processor, CronTrigger(hour=0,  minute=1),  id="recurring")
    scheduler.add_job(job_morning_digest,       CronTrigger(hour=settings.morning_digest_hour, minute=0), id="morning")
    scheduler.add_job(job_overdue_check,        CronTrigger(hour=settings.overdue_check_hour,  minute=0), id="overdue")
    scheduler.add_job(job_weekly_review,        CronTrigger(day_of_week="sun", hour=settings.overdue_check_hour, minute=0), id="weekly")
    scheduler.start()
    logger.info(
        "scheduler started — recurring@00:01, morning@%02d:00, overdue@%02d:00, weekly@Sun %02d:00 (%s)",
        settings.morning_digest_hour, settings.overdue_check_hour, settings.overdue_check_hour,
        settings.scheduler_timezone,
    )
