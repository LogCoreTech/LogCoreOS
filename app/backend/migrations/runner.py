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
                updates["career_history"] = [
                    {
                        "title": personal.get("occupation") or "",
                        "industry": career_fields.get("industry", ""),
                        "education": education,
                        "years_experience": career_fields.get("years_experience", ""),
                        "skills": career_fields.get("skills", ""),
                        "archived": False,
                    }
                ]

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


def m010_seed_home_dashboards(brain: Path) -> None:
    """Seed one 'Home' dashboard per existing user x workspace they have,
    replicating today's fixed Dashboard.jsx widgets as blocks, and set it as
    that user's default_dashboard_id for that workspace. Idempotent per
    user+workspace (skips if they already have any dashboard there); one
    user's failure never blocks the rest."""
    import uuid

    from services import auth_service, dashboards_service
    from services.file_service import brain_path as _brain_path

    # Route dashboards_service's file I/O through the SAME brain root the
    # migration runner was invoked with (matters for tests using a temp brain).
    if brain != _brain_path():
        return

    users_dir = brain / "USERS"
    if not users_dir.exists():
        return

    def _lg(x, y, w, h):
        return {"x": x, "y": y, "w": w, "h": h}

    def _sm(y):
        return {"x": 0, "y": y, "w": 2, "h": 3}

    seeded = 0
    for user in auth_service.list_users():
        name = user["name"]
        record = auth_service.get_user_by_name(name) or {}
        default_map = dict(record.get("default_dashboard_id") or {})
        changed_default = False
        for workspace in record.get("workspaces", ["personal"]):
            try:
                if dashboards_service.list_dashboards(name, workspace):
                    continue  # already has one — never overwrite

                blocks = [
                    {
                        "id": str(uuid.uuid4()),
                        "type": "top3_tasks",
                        "config": {"scope": "viewer"},
                        "layout": {"lg": _lg(0, 0, 4, 3), "sm": _sm(0)},
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "type": "due_today",
                        "config": {"scope": "viewer"},
                        "layout": {"lg": _lg(4, 0, 4, 3), "sm": _sm(3)},
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "type": "streaks",
                        "config": {"scope": "viewer"},
                        "layout": {"lg": _lg(8, 0, 4, 3), "sm": _sm(6)},
                    },
                ]
                if workspace == "personal":
                    blocks.append(
                        {
                            "id": str(uuid.uuid4()),
                            "type": "home_assistant_favourites",
                            "config": {"scope": "viewer"},
                            "layout": {"lg": _lg(0, 3, 6, 3), "sm": _sm(9)},
                        }
                    )
                else:
                    blocks.append(
                        {
                            "id": str(uuid.uuid4()),
                            "type": "pool_tasks",
                            "config": {},
                            "layout": {"lg": _lg(0, 3, 6, 3), "sm": _sm(9)},
                        }
                    )
                blocks.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "my_assets_summary",
                        "config": {"scope": "viewer"},
                        "layout": {"lg": _lg(6, 3, 6, 3), "sm": _sm(12)},
                    }
                )

                dashboard = dashboards_service.create_dashboard(name, workspace, name, "Home", "🏠")
                dashboards_service.update_dashboard(
                    name, workspace, dashboard["id"], {"blocks": blocks}, by=name
                )
                if workspace not in default_map:
                    default_map[workspace] = dashboard["id"]
                    changed_default = True
                seeded += 1
            except Exception:
                logger.exception(
                    "m010: failed to seed Home dashboard for %r/%r — skipping", name, workspace
                )
        if changed_default:
            try:
                auth_service.update_user(user["id"], {"default_dashboard_id": default_map})
            except Exception:
                logger.exception("m010: failed to set default_dashboard_id for %r", name)

    if seeded:
        logger.info("m010: seeded %d Home dashboard(s)", seeded)


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
def m011_rescale_dashboard_grid_units(brain: Path) -> None:
    """Dashboard grid moved from 12 cols/80px rows to 36 cols/24px rows (finer
    positioning/resizing). Every already-saved block layout predates this and
    is expressed in the OLD units — reinterpreted against the new grid they'd
    render as tiny slivers clustered in the top-left corner. Multiply every
    saved block's layout.lg/layout.sm x/y/w/h by 3 (the scale factor) so
    existing dashboards keep their visual position/size. Covers every user
    store AND both pool stores (_household/_team) via _all_stores() — m010's
    narrower per-user-workspace loop would miss pool dashboards entirely."""
    from services import dashboards_service
    from services.file_service import brain_path as _brain_path

    if brain != _brain_path():
        return

    SCALE = 3

    def _scale(v: dict) -> dict:
        return {k: (v[k] * SCALE if k in ("x", "y", "w", "h") else v[k]) for k in v}

    rescaled = 0
    for store_user, workspace in dashboards_service._all_stores():
        try:
            dashboards = dashboards_service.list_dashboards(store_user, workspace)
            for d in dashboards:
                new_blocks = []
                changed = False
                for b in d.get("blocks", []):
                    layout = b.get("layout") or {}
                    new_layout = dict(layout)
                    if "lg" in layout:
                        new_layout["lg"] = _scale(layout["lg"])
                        changed = True
                    if "sm" in layout:
                        new_layout["sm"] = _scale(layout["sm"])
                        changed = True
                    new_blocks.append({**b, "layout": new_layout})
                if changed:
                    dashboards_service.update_dashboard(
                        store_user, workspace, d["id"], {"blocks": new_blocks}
                    )
                    rescaled += 1
        except Exception:
            logger.exception(
                "m011: failed to rescale dashboards for %r/%r — skipping", store_user, workspace
            )

    if rescaled:
        logger.info("m011: rescaled %d dashboard(s) to the new grid units", rescaled)


def m012_rescale_dashboard_mobile_grid_units(brain: Path) -> None:
    """Mobile dashboard grid moved from 2 cols (never actually read — layout.sm
    was always ignored at render time, ever since Custom Dashboards shipped;
    the frontend hardcoded an auto-stack instead) to 12 cols (real mobile
    drag/resize, layout.sm now genuinely read/written).

    Deliberately NOT a multiply like m011 — every stored sm.x/w's provenance
    is ambiguous by the time this runs: some predate m011 (x:0, w:2), some
    were blindly ×3'd BY m011 itself (x:0, w:6, since m011 rescaled whatever
    layout.sm dict it found without knowing it was dead data), and any block
    added through the UI between m011 shipping and this migration shipping
    used addBlock()'s then-current hardcoded w:2 default again. All three
    are pre-real-mobile-editing artifacts with the same one true meaning —
    "full width, stacked" was the ONLY value the UI ever showed, since mobile
    was never actually interactive — so normalizing x/w to a fixed full-width
    value is correct regardless of which artifact a given block has, and
    sidesteps needing to know which. y/h are untouched: rowHeight didn't
    change again here, so m011's earlier ×3 on those is still correct.

    Bonus property this approach has that m011's multiply doesn't: setting a
    fixed value is idempotent. Running this twice is harmless.
    """
    from services import dashboards_service
    from services.file_service import brain_path as _brain_path

    if brain != _brain_path():
        return

    MOBILE_COLS = 12

    rescaled = 0
    for store_user, workspace in dashboards_service._all_stores():
        try:
            dashboards = dashboards_service.list_dashboards(store_user, workspace)
            for d in dashboards:
                new_blocks = []
                changed = False
                for b in d.get("blocks", []):
                    layout = b.get("layout") or {}
                    sm = layout.get("sm")
                    if sm and (sm.get("x") != 0 or sm.get("w") != MOBILE_COLS):
                        new_layout = dict(layout)
                        new_layout["sm"] = {**sm, "x": 0, "w": MOBILE_COLS}
                        new_blocks.append({**b, "layout": new_layout})
                        changed = True
                    else:
                        new_blocks.append(b)
                if changed:
                    dashboards_service.update_dashboard(
                        store_user, workspace, d["id"], {"blocks": new_blocks}
                    )
                    rescaled += 1
        except Exception:
            logger.exception(
                "m012: failed to rescale mobile layout for %r/%r — skipping", store_user, workspace
            )

    if rescaled:
        logger.info("m012: normalized mobile grid units for %d dashboard(s)", rescaled)


def m013_move_self_contacts_to_household_pool(brain: Path) -> None:
    """Self-contacts move from each user's own personal store into the shared
    _household pool (2026-08-17) — "always on household" and "survives
    account deletion" both become free once storage itself lives there, and
    every user's contact becomes reachable from both workspaces the same way
    any other forced-cross_workspace pool record is. Idempotent per-user
    (skipped if already found via the now-household-scanning
    get_self_contact()); relocates the contact record, its own interactions/
    deals entries, and its photo file. Hand-rolled, NOT transfer_ownership()
    — that explicitly rejects self_of contacts, since a self-contact's
    identity/lock invariants don't match an ordinary ownership transfer.
    Mirrors transfer_ownership()'s own share-field conversion (shared_with ->
    contributors) since the destination is a pool. One user's failure never
    blocks the rest."""
    from services import contacts_service
    from services.file_service import brain_path as _brain_path
    from services.file_service import (
        contact_deals_path,
        contact_interactions_path,
        contact_photo_path,
        contacts_path,
    )

    if brain != _brain_path():
        return

    users_dir = brain / "USERS"
    if not users_dir.exists():
        return

    moved = 0
    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir() or user_dir.name.startswith("_"):
            continue
        name = user_dir.name
        try:
            if contacts_service.get_self_contact(name) is not None:
                continue  # already in the household pool — nothing to do

            own_path = contacts_path(name, "personal")
            own_data = read_json(own_path, default={"contacts": []})
            own_list = own_data.get("contacts", [])
            idx = next((i for i, c in enumerate(own_list) if c.get("self_of") == name), None)
            if idx is None:
                continue  # never completed setup / never had one — nothing to migrate

            contact = own_list.pop(idx)
            contact["cross_workspace"] = True
            converted_contributors = list(contact.get("contributors") or [])
            for share in contact.get("shared_with") or []:
                converted_contributors.append(
                    {"target": share["target"], "access": share.get("access", "read")}
                )
            contact["contributors"] = converted_contributors
            contact["shared_with"] = []
            write_json(own_path, {"contacts": own_list})

            household_path = contacts_path(contacts_service.POOL_HOUSEHOLD, "personal")
            household_data = read_json(household_path, default={"contacts": []})
            household_list = household_data.get("contacts", [])
            household_list.append(contact)
            write_json(household_path, {"contacts": household_list})

            for path_fn, key in (
                (contact_interactions_path, "interactions"),
                (contact_deals_path, "deals"),
            ):
                src_path = path_fn(name, "personal")
                src_data = read_json(src_path, default={key: []})
                src_items = src_data.get(key, [])
                moving = [x for x in src_items if x.get("contact_id") == contact["id"]]
                if not moving:
                    continue
                remaining = [x for x in src_items if x.get("contact_id") != contact["id"]]
                write_json(src_path, {key: remaining})
                dest_path = path_fn(contacts_service.POOL_HOUSEHOLD, "personal")
                dest_data = read_json(dest_path, default={key: []})
                write_json(dest_path, {key: dest_data.get(key, []) + moving})

            ext = contact.get("photo_ext")
            if ext:
                src_photo = contact_photo_path(name, "personal", contact["id"], ext)
                if src_photo.exists():
                    dest_photo = contact_photo_path(
                        contacts_service.POOL_HOUSEHOLD, "personal", contact["id"], ext
                    )
                    dest_photo.parent.mkdir(parents=True, exist_ok=True)
                    src_photo.replace(dest_photo)

            moved += 1
        except Exception:
            logger.exception(
                "m013: failed to move self-contact to household pool for %r — skipping", name
            )

    if moved:
        from services import contacts_index

        contacts_index.rebuild_share_index()
        logger.info("m013: moved %d self-contact(s) into the household pool", moved)


def m014_core_values_to_list(brain: Path) -> None:
    """`core_values` changed from a comma-separated string to a list of pill
    entries (2026-08-17) — split any existing string value the same way
    contacts_service._validate_core_values() now would, across every contact
    store: every real user's own personal + business stores, and both pool
    stores (_household/_team, self-contacts included since m013 moved them
    there). Already-list values (nothing to do, including a from-scratch
    install with no legacy data) and non-string/falsy values are left alone.
    One store's failure never blocks the rest."""
    from services import contacts_service
    from services.file_service import brain_path as _brain_path
    from services.file_service import contacts_path

    if brain != _brain_path():
        return

    def _convert(owner: str, workspace: str) -> int:
        path = contacts_path(owner, workspace)
        data = read_json(path, default=None)
        if data is None:
            return 0
        contacts = data.get("contacts", [])
        changed = False
        for c in contacts:
            v = c.get("core_values")
            if isinstance(v, str):
                deduped: list[str] = []
                for s in v.split(","):
                    s = s.strip()
                    if s and s not in deduped:
                        deduped.append(s)
                c["core_values"] = deduped
                changed = True
        if changed:
            write_json(path, {"contacts": contacts})
        return 1 if changed else 0

    users_dir = brain / "USERS"
    stores = [
        (contacts_service.POOL_HOUSEHOLD, "personal"),
        (contacts_service.POOL_TEAM, "business"),
    ]
    if users_dir.exists():
        for user_dir in users_dir.iterdir():
            if not user_dir.is_dir() or user_dir.name.startswith("_"):
                continue
            stores.append((user_dir.name, "personal"))
            stores.append((user_dir.name, "business"))

    converted = 0
    for owner, workspace in stores:
        try:
            converted += _convert(owner, workspace)
        except Exception:
            logger.exception(
                "m014: failed to convert core_values for %r/%r — skipping", owner, workspace
            )

    if converted:
        logger.info("m014: converted core_values to a list in %d contact store(s)", converted)


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
    ("m010_seed_home_dashboards", m010_seed_home_dashboards),
    ("m011_rescale_dashboard_grid_units", m011_rescale_dashboard_grid_units),
    ("m012_rescale_dashboard_mobile_grid_units", m012_rescale_dashboard_mobile_grid_units),
    ("m013_move_self_contacts_to_household_pool", m013_move_self_contacts_to_household_pool),
    ("m014_core_values_to_list", m014_core_values_to_list),
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


def _run_list(brain: Path, migrations: list[tuple[str, MigrationFn]]) -> int:
    """Run every not-yet-applied migration in `migrations` against `brain`,
    tracking completion in the same shared migrations.json state file
    regardless of which list (core or a module's) a migration came from.
    Namespacing (a module's own "modid:m001_..." naming convention) is what
    keeps two lists' names from colliding — see module_registry.py's
    boot-time collision check, which excludes a module before it ever gets
    here if that convention was violated."""
    state_path = _state_path(brain)
    state = read_json(state_path, default={"applied": []})
    applied: list[str] = state.get("applied", [])
    applied_set = set(applied)

    count = 0
    for name, fn in migrations:
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

    return count


def _module_migrations() -> list[tuple[str, MigrationFn]]:
    """Migrations from every DISCOVERED module_packages/ module — present on
    disk, not just installed. A module's migration must run at every boot
    regardless of install state, same as core migrations always run
    regardless of which features are toggled (e.g. a locked module's own
    upgrade migration is what MARKS it installed in the first place)."""
    from module_registry import discover_manifests

    manifests, _errors = discover_manifests()
    out: list[tuple[str, MigrationFn]] = []
    for manifest in manifests.values():
        out.extend(manifest.migrations)
    return out


def _run_pending_locked(brain: Path) -> int:
    count = _run_list(brain, MIGRATIONS)
    count += _run_list(brain, _module_migrations())
    if count:
        logger.info("Applied %d migration(s).", count)
    return count
