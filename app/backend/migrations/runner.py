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


def m005_asset_template_ids(brain: Path) -> None:
    """Backfill a stable `id` (+ owner/shared_with/restrict_roles) on existing global
    asset templates so they can be referenced by id alongside per-user templates."""
    import uuid

    tpl_file = brain / "_system" / "asset_templates.json"
    if not tpl_file.exists():
        return
    data = read_json(tpl_file, default={"templates": []})
    changed = False
    for t in data.get("templates", []):
        if not t.get("id"):
            t["id"] = str(uuid.uuid4())
            changed = True
        for key, default in (("owner", "_global"), ("shared_with", []), ("restrict_roles", [])):
            if key not in t:
                t[key] = default if not isinstance(default, list) else list(default)
                changed = True
    if changed:
        write_json(tpl_file, data)


def m006_seed_folder_template(brain: Path) -> None:
    """Seed a default global 'Folder' asset template (name + notes only, no
    custom fields) so users can organize assets without building a template
    first. Seeded once — an admin who deletes it won't see it come back."""
    import uuid
    from datetime import datetime, timezone

    tpl_file = brain / "_system" / "asset_templates.json"
    data = read_json(tpl_file, default={"templates": []})
    templates = data.setdefault("templates", [])
    if any(t.get("key") == "folder" for t in templates):
        return
    templates.append(
        {
            "id": str(uuid.uuid4()),
            "key": "folder",
            "label": "Folder",
            "icon": "📁",
            "fields": [],
            "owner": "_global",
            "shared_with": [],
            "restrict_roles": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    write_json(tpl_file, data)


def m007_finance_guest_disabled(brain: Path) -> None:
    """Disable the new finance module for the built-in guest role on existing
    installs. Money data is the most sensitive in the app — guests must be
    granted access explicitly. Runs once; an admin re-enabling it sticks."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return  # fresh install — init_features() seeds guest with finance off
    data = read_json(features_file, default={})
    roles = data.get("roles") or {}
    guest = roles.get("guest")
    if guest is None or "finance" in guest:
        return
    guest["finance"] = False
    write_json(features_file, data)


def m009_migrate_profiles_to_self_contacts(brain: Path) -> None:
    """Merge each real user's Profile (profile.json) into a new self-contact —
    a Contact record marked self_of=<user>, the single source of truth going
    forward. Idempotent per-user (skips if a self-contact already exists) and
    never touches/deletes the old profile.json/Profile.md files. One user's
    failure never blocks the rest."""
    from services import contacts_service
    from services.file_service import read_json, ws_path

    users_dir = brain / "USERS"
    if not users_dir.exists():
        return

    field_map = {
        "pronouns": "pronouns",
        "city": "city",
        "state": "state",
        "country": "country",
        "occupation": "occupation",
        "marital_status": "marital_status",
        "pets": "pets",
        "life_mission": "life_mission",
        "core_values": "core_values",
        "key_constraints": "key_constraints",
        "wake_weekday": "wake_weekday",
        "wake_weekend": "wake_weekend",
        "bedtime": "bedtime",
        "blood_type": "blood_type",
        "conditions": "conditions",
        "medications": "medications",
        "diet": "diet",
        "exercise": "exercise",
        "income_range": "income_range",
        "budget_style": "budget_style",
        "communication_style": "communication_style",
        "tone": "tone",
        "response_language": "response_language",
        "topics_to_emphasize": "topics_to_emphasize",
        "topics_to_avoid": "topics_to_avoid",
        "notes": "notes",
    }
    # Not migrated: old free-text `height`/`weight`/`work_hours` — the new
    # schema needs structured numbers/times (height_cm, work_start/end) and
    # there's no reliable way to parse "5'11", 175 lbs" or "8 AM - 5 PM" into
    # that shape. No real installs have used the merged Profile yet (shipped
    # this same day), so this is an acceptable one-time loss, not a
    # regression against real user data.

    migrated = 0
    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir() or user_dir.name.startswith("_"):
            continue
        name = user_dir.name
        try:
            if contacts_service.get_self_contact(name) is not None:
                continue  # already migrated (or lazily created) — never overwrite

            personal = read_json(ws_path(name, "personal") / "profile.json", default={})
            business = read_json(ws_path(name, "business") / "profile.json", default={})

            updates: dict = {}
            for src_key, dst_key in field_map.items():
                if personal.get(src_key):
                    updates[dst_key] = personal[src_key]
            if personal.get("dob") and not updates.get("birthday"):
                updates["birthday"] = personal["dob"]
            if personal.get("phone"):
                updates["phones"] = [str(personal["phone"])]

            # Old flat employer/industry/education/years_experience/skills
            # become a single "current" career_history entry, if any are set.
            career_fields = {
                k: personal[k]
                for k in ("employer", "industry", "education", "years_experience", "skills")
                if personal.get(k)
            }
            if career_fields:
                education = career_fields.get("education", "")
                if education not in contacts_service.EDUCATION_LEVELS:
                    education = ""  # legacy free text didn't match the new fixed list
                updates["career_history"] = [{
                    "title": personal.get("occupation") or "",
                    "industry": career_fields.get("industry", ""),
                    "education": education,
                    "years_experience": career_fields.get("years_experience", ""),
                    "skills": career_fields.get("skills", ""),
                    "archived": False,
                }]

            priority_order: dict = {}
            if personal.get("priority_order"):
                priority_order["personal"] = personal["priority_order"]
            if business.get("priority_order"):
                priority_order["business"] = business["priority_order"]
            if priority_order:
                updates["priority_order"] = priority_order

            occupation = updates.pop("occupation", None)
            contact = contacts_service.create_self_contact(name, occupation=occupation)
            if updates:
                contacts_service.update_contact(name, "personal", contact["id"], updates)
            migrated += 1
        except Exception:
            logger.exception("m009: failed to migrate profile for user %r — skipping", name)

    if migrated:
        logger.info("m009: migrated %d user profile(s) into self-contacts", migrated)


def m008_contacts_guest_disabled(brain: Path) -> None:
    """Disable the new Contacts (CRM) module for the built-in guest role on
    existing installs — contacts hold PII, so guests must be granted access
    explicitly. Runs once; an admin re-enabling it sticks."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return  # fresh install — init_features() seeds guest with contacts off
    data = read_json(features_file, default={})
    roles = data.get("roles") or {}
    guest = roles.get("guest")
    if guest is None or "contacts" in guest:
        return
    guest["contacts"] = False
    write_json(features_file, data)


# Ordered list — append new migrations here; never reorder or remove
MIGRATIONS: list[tuple[str, MigrationFn]] = [
    ("m001_task_type_field", m001_task_type_field),
    ("m002_task_notes_field", m002_task_notes_field),
    ("m003_user_disabled_modules", m003_user_disabled_modules),
    ("m004_task_due_time_field", m004_task_due_time_field),
    ("m005_asset_template_ids", m005_asset_template_ids),
    ("m006_seed_folder_template", m006_seed_folder_template),
    ("m007_finance_guest_disabled", m007_finance_guest_disabled),
    ("m008_contacts_guest_disabled", m008_contacts_guest_disabled),
    ("m009_migrate_profiles_to_self_contacts", m009_migrate_profiles_to_self_contacts),
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
