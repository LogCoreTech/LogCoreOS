"""Onboarding seed data (item #11, 2026-09-04 UX Polish Batch) — one example
item per module, created via each module's own real creation function (never
a raw file write, so it's validated exactly like anything a user creates),
called from that module's own on_new_user() hook. Every seed item's
name/title is prefixed "Example: " so it's obviously safe to delete.

Deliberately NOT called for Household/Team (shared pools, not personal data),
Chat/Dashboards (structural, no natural "one example item"), or Home
Assistant/Automations (need a real external connection, can't fake one) —
see docs/TASKS.md's UX Polish Batch section for the full disposition.
"""

from datetime import timedelta

from services.auth_service import today_for_user

_PREFIX = "Example: "


def seed_task(user_name: str, workspace: str = "personal") -> None:
    from services.task_service import add_task

    add_task(
        user_name,
        {"title": f"{_PREFIX}Water the plants", "category": "Personal"},
        workspace,
    )


def seed_note(user_name: str, workspace: str = "personal") -> None:
    from services.notes_service import create_note

    # Notes' 2nd arg is a filesystem PATH, not a display title — a colon
    # (used everywhere else in this file's own _PREFIX) isn't a valid path
    # character (services/notes_service.py's _SEGMENT_RE), so this one spells
    # the prefix differently.
    create_note(
        user_name,
        "Example - Welcome to Notes",
        "This is an example note — feel free to edit or delete it.",
        workspace,
    )


def seed_journal_entry(user_name: str, workspace: str = "personal") -> None:
    from module_packages.journal.backend.service import upsert_entry

    today = today_for_user(user_name).isoformat()
    upsert_entry(
        user_name,
        today,
        f"{_PREFIX}This is what a journal entry looks like. Write freely — only you can ever read this.",
        workspace,
    )


def seed_calendar_event(user_name: str, workspace: str = "personal") -> None:
    from services.events_service import add_event

    start = (today_for_user(user_name) + timedelta(days=1)).isoformat()
    add_event(user_name, {"title": f"{_PREFIX}Team meeting", "start_date": start}, workspace)


def seed_goal(user_name: str, workspace: str = "personal") -> None:
    from module_packages.goals.backend.service import create_goal

    due = (today_for_user(user_name) + timedelta(days=30)).isoformat()
    create_goal(
        user_name,
        {"title": f"{_PREFIX}Read one book this month", "due_date": due},
        workspace,
    )


def seed_asset(user_name: str, workspace: str = "personal") -> None:
    from services.assets_service import create_asset

    create_asset(
        user_name,
        {
            "name": f"{_PREFIX}My first asset",
            "notes": "Assets can be anything worth tracking — a vehicle, a property, equipment.",
        },
        workspace,
        created_by=user_name,
    )


def seed_contact(user_name: str, workspace: str = "personal") -> None:
    from services.contacts_service import create_contact

    create_contact(
        user_name,
        workspace,
        {
            "type": "person",
            "name": f"{_PREFIX}Jane Doe",
            "notes": "An example contact — edit or delete it anytime.",
        },
        created_by=user_name,
    )


def seed_finance_book(user_name: str, workspace: str = "personal") -> None:
    from services.finance_service import create_book

    create_book(user_name, workspace, f"{_PREFIX}My First Book", created_by=user_name)
