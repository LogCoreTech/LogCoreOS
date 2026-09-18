"""Nightly recurring task processor — advances due dates, manages streaks, and logs
completed/missed occurrences (see services/recurrence_engine.py for the date math and
services/task_service.py's append_log_entry for the log's shared dedup+cap logic)."""

import logging

from services.auth_service import today_for_user
from services.file_service import (
    brain_path,
    history_path,
    read_json,
    tasks_path,
    update_json,
    write_json,
)
from services.recurrence_engine import first_occurrence_on_or_after, next_occurrence
from services.task_service import append_log_entry

logger = logging.getLogger(__name__)


def process_user(user_name: str) -> dict:
    """Routed through file_service.update_json() (2026-09-16) — same
    read-modify-write lock task_service.py's add_task/update_task/delete_task
    already use on this exact file. This job runs unattended at midnight
    against tasks.json while a user's own interactive edit could land on the
    same file at the same moment; the previous plain read_json()+write_json()
    pair here left that race open (write_json()'s own lock only covers the
    write itself, not the read that preceded it) even though the interactive
    side was already safe."""
    today = today_for_user(user_name).isoformat()
    path = tasks_path(user_name)
    advanced = 0
    broken = 0

    def _process(data: dict) -> dict:
        nonlocal advanced, broken

        # Archive done non-recurring tasks completed before today.
        tasks_to_archive = []
        for t in data["tasks"]:
            if t.get("type") == "recurring" or t.get("status") != "done":
                continue
            completed_date = (t.get("completed_at") or "")[:10]
            if completed_date and completed_date < today:
                tasks_to_archive.append(t)
        if tasks_to_archive:
            hist = read_json(history_path(user_name), default={"tasks": []})
            hist["tasks"].extend(tasks_to_archive)
            write_json(history_path(user_name), hist)
            archive_ids = {t["id"] for t in tasks_to_archive}
            data["tasks"] = [t for t in data["tasks"] if t["id"] not in archive_ids]

        for task in data["tasks"]:
            if task.get("type") != "recurring":
                continue
            try:
                rule = task.get("recurrence") or {"freq": "daily", "interval": 1}

                if task.get("due_date") is None:
                    # Self-heal: a recurring task should always carry a real due_date once
                    # created (see task_service.add_task()) — this backfills one for a task
                    # that somehow ended up without (pre-fix data, or a bypassed-validation
                    # write), instead of leaving it stuck with no due date forever.
                    task["due_date"] = first_occurrence_on_or_after(today, rule)
                    continue

                due = task["due_date"]

                if (
                    task.get("status") == "done"
                    and task.get("last_completed_date")
                    and task.get("last_completed_date") < today
                ):
                    task["due_date"] = next_occurrence(due, rule)
                    task["status"] = "pending"
                    advanced += 1
                elif task.get("status") == "pending" and due < today:
                    # The occurrence due on `due` was never completed — log it as missed
                    # before advancing. Real bug fixed 2026-08-31 (owner-reported: "it
                    # skipped today and went to tomorrow"): this used to call
                    # next_occurrence(today, rule), which finds the occurrence STRICTLY
                    # AFTER its anchor — correct for chaining from a real prior occurrence,
                    # but today hasn't happened yet, so for a daily task that unconditionally
                    # skipped straight to tomorrow even though today itself is a perfectly
                    # valid occurrence; for a weekly task landing on today's own weekday it
                    # did the same thing. first_occurrence_on_or_after uses inclusive
                    # on-or-after semantics instead, which is what "the next time this
                    # should happen, at the earliest today" actually means.
                    task["completion_log"] = append_log_entry(
                        task.get("completion_log"), due, "missed"
                    )
                    task["streak_count"] = 0
                    task["due_date"] = first_occurrence_on_or_after(today, rule)
                    broken += 1
            except (ValueError, KeyError, TypeError):
                logger.exception(
                    "recurring_service: failed to advance task %s for user %s — skipping",
                    task.get("id"),
                    user_name,
                )
                continue

        return data

    update_json(path, _process, default={"tasks": []})
    return {"user": user_name, "advanced": advanced, "broken_streaks": broken}


def process_all_users() -> list[dict]:
    users_dir = brain_path() / "USERS"
    results = []
    for user_dir in users_dir.iterdir():
        if user_dir.name.startswith("_") or not user_dir.is_dir():
            continue
        tp = tasks_path(user_dir.name)
        if tp.exists():
            results.append(process_user(user_dir.name))
    return results
