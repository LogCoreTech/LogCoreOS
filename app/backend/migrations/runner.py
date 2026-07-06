"""
Schema migration runner for the LogCore Brain file store.

Migrations are plain functions registered in MIGRATIONS below.
Each runs exactly once; completion is tracked in brain/_system/migrations.json.
"""

import fcntl
import logging
from pathlib import Path
from typing import Callable

from services.file_service import brain_path, read_json, write_json

logger = logging.getLogger("logcore.migrations")

MigrationFn = Callable[[Path], None]

# ── Migration definitions ──────────────────────────────────────────────────────


def m001_task_type_field(brain: Path) -> None:
    """Ensure every active task has a `type` field (default: 'todo')."""
    users_dir = brain / "USERS"
    if not users_dir.exists():
        return
    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir():
            continue
        tasks_file = user_dir / "Tasks" / "tasks.json"
        if not tasks_file.exists():
            continue
        data = read_json(tasks_file, default={"tasks": []})
        changed = False
        for task in data.get("tasks", []):
            if "type" not in task:
                task["type"] = "todo"
                changed = True
        if changed:
            write_json(tasks_file, data)


def m002_task_notes_field(brain: Path) -> None:
    """Ensure every task has a `notes` field (default: None)."""
    users_dir = brain / "USERS"
    if not users_dir.exists():
        return
    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir():
            continue
        for fname in ("tasks.json", "tasks_history.json"):
            tasks_file = user_dir / "Tasks" / fname
            if not tasks_file.exists():
                continue
            data = read_json(tasks_file, default={"tasks": []})
            changed = False
            for task in data.get("tasks", []):
                if "notes" not in task:
                    task["notes"] = None
                    changed = True
            if changed:
                write_json(tasks_file, data)


def m003_user_disabled_modules(brain: Path) -> None:
    """Ensure every user record has a `disabled_modules` list."""
    auth_file = brain / "_system" / "auth.json"
    if not auth_file.exists():
        return
    data = read_json(auth_file, default={"users": []})
    changed = False
    for user in data.get("users", []):
        if "disabled_modules" not in user:
            user["disabled_modules"] = []
            changed = True
    if changed:
        write_json(auth_file, data)


def m004_task_due_time_field(brain: Path) -> None:
    """Ensure every task has a `due_time` field (default: None)."""
    users_dir = brain / "USERS"
    if not users_dir.exists():
        return
    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir():
            continue
        for fname in ("tasks.json", "tasks_history.json"):
            tasks_file = user_dir / "Tasks" / fname
            if not tasks_file.exists():
                continue
            data = read_json(tasks_file, default={"tasks": []})
            changed = False
            for task in data.get("tasks", []):
                if "due_time" not in task:
                    task["due_time"] = None
                    changed = True
            if changed:
                write_json(tasks_file, data)


# Ordered list — append new migrations here; never reorder or remove
MIGRATIONS: list[tuple[str, MigrationFn]] = [
    ("m001_task_type_field", m001_task_type_field),
    ("m002_task_notes_field", m002_task_notes_field),
    ("m003_user_disabled_modules", m003_user_disabled_modules),
    ("m004_task_due_time_field", m004_task_due_time_field),
]

# ── Runner ─────────────────────────────────────────────────────────────────────


def _state_path(brain: Path) -> Path:
    p = brain / "_system" / "migrations.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def run_pending(brain: Path | None = None) -> int:
    """Run all pending migrations. Returns the number of migrations applied."""
    if brain is None:
        brain = brain_path()

    lock_path = brain / "_system" / "migrations.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            return _run_pending_locked(brain)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _run_pending_locked(brain: Path) -> int:
    state_path = _state_path(brain)
    state = read_json(state_path, default={"applied": []})
    applied: list[str] = state.get("applied", [])
    applied_set = set(applied)

    count = 0
    for name, fn in MIGRATIONS:
        if name in applied_set:
            continue
        try:
            logger.info("Running migration: %s", name)
            fn(brain)
            applied.append(name)
            state["applied"] = applied
            write_json(state_path, state)
            count += 1
            logger.info("Migration completed: %s", name)
        except Exception as exc:
            logger.error(
                "Migration %s FAILED: %s — skipping and continuing", name, exc, exc_info=True
            )

    if count:
        logger.info("Applied %d migration(s).", count)
    return count
