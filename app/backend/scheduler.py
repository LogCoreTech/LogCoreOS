"""APScheduler background jobs — recurring processor, digests, overdue alerts."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from services.file_service import brain_path, tasks_path, read_json
from services.priority_service import get_top3
from services.recurring_service import process_all_users
from services.notification_service import send

scheduler = BackgroundScheduler(timezone="America/Chicago")


def _all_users() -> list[str]:
    users_dir = brain_path() / "USERS"
    return [
        d.name for d in users_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_")
        and tasks_path(d.name).exists()
    ]


def _ntfy_channel(user_name: str) -> str:
    return f"logcore-{user_name.lower().replace(' ', '-')}"


def job_recurring_processor():
    results = process_all_users()
    print(f"[scheduler] recurring processor: {results}")


def job_morning_digest():
    from datetime import date
    today = date.today().strftime("%A, %B %-d")
    for user in _all_users():
        try:
            top3 = get_top3(user)
            if not top3:
                continue
            lines = "\n".join(f"{i+1}. [{t['category']}] {t['title']}" for i, t in enumerate(top3))
            send(
                channel=_ntfy_channel(user),
                title=f"Good morning, {user.split()[0]}! — {today}",
                message=f"Your top 3 today:\n\n{lines}",
                priority="default",
            )
        except Exception as e:
            print(f"[scheduler] morning digest error for {user}: {e}")


def job_overdue_check():
    from datetime import date
    today = date.today().isoformat()
    for user in _all_users():
        try:
            data = read_json(tasks_path(user))
            overdue = [
                t for t in data.get("tasks", [])
                if t.get("status") == "pending"
                and t.get("due_date")
                and t["due_date"] < today
            ]
            if not overdue:
                continue
            lines = "\n".join(f"• [{t['category']}] {t['title']} (due {t['due_date']})" for t in overdue)
            send(
                channel=_ntfy_channel(user),
                title=f"{len(overdue)} overdue task{'s' if len(overdue) > 1 else ''}",
                message=lines,
                priority="high",
            )
        except Exception as e:
            print(f"[scheduler] overdue check error for {user}: {e}")


def job_weekly_review():
    from datetime import date, timedelta
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    for user in _all_users():
        try:
            from services.file_service import history_path
            history_file = history_path(user)
            if not history_file.exists():
                continue
            history = read_json(history_file).get("tasks", [])
            this_week = [t for t in history if (t.get("completed_at") or "") >= week_ago]
            if not this_week:
                continue
            by_cat = {}
            for t in this_week:
                by_cat.setdefault(t["category"], 0)
                by_cat[t["category"]] += 1
            lines = "\n".join(f"• {cat}: {count} task{'s' if count>1 else ''}" for cat, count in sorted(by_cat.items(), key=lambda x: -x[1]))
            send(
                channel=_ntfy_channel(user),
                title=f"Weekly review — {len(this_week)} tasks completed",
                message=f"Great week, {user.split()[0]}!\n\n{lines}",
                priority="default",
            )
        except Exception as e:
            print(f"[scheduler] weekly review error for {user}: {e}")


def start():
    scheduler.add_job(job_recurring_processor, CronTrigger(hour=0,  minute=1),  id="recurring")
    scheduler.add_job(job_morning_digest,       CronTrigger(hour=6,  minute=0),  id="morning")
    scheduler.add_job(job_overdue_check,        CronTrigger(hour=19, minute=0),  id="overdue")
    scheduler.add_job(job_weekly_review,        CronTrigger(day_of_week="sun", hour=19, minute=0), id="weekly")
    scheduler.start()
    print("[scheduler] started — recurring@00:01, morning@06:00, overdue@19:00, weekly@Sun 19:00")
