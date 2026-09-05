"""Tests for services/seed_data_service.py — one seeded example item per
module at account creation (item #11, 2026-09-04 UX Polish Batch)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import services.seed_data_service as svc

USER = "TestUser"


def test_seed_task(brain):
    from services.task_service import list_tasks

    svc.seed_task(USER)
    tasks = list_tasks(USER)
    assert len(tasks) == 1
    assert tasks[0]["title"].startswith("Example: ")


def test_seed_note(brain):
    from services.notes_service import list_notes

    svc.seed_note(USER)
    notes = list_notes(USER, "personal")
    assert len(notes) == 1
    assert notes[0]["name"].startswith("Example")  # "Example - ..." (colon isn't a valid path char)


def test_seed_journal_entry(brain):
    from module_packages.journal.backend.service import list_entries

    svc.seed_journal_entry(USER)
    entries = list_entries(USER)
    assert len(entries) == 1


def test_seed_calendar_event(brain):
    from services.events_service import list_events

    svc.seed_calendar_event(USER)
    events = list_events(USER)
    assert len(events) == 1
    assert events[0]["title"].startswith("Example: ")


def test_seed_goal(brain):
    from module_packages.goals.backend.service import list_goals

    svc.seed_goal(USER)
    goals = list_goals(USER, "personal")
    assert len(goals) == 1
    assert goals[0]["title"].startswith("Example: ")
    assert goals[0]["due_date"] is not None  # a good example sets one, even though not required


def test_seed_asset(brain):
    from services.assets_service import list_assets

    svc.seed_asset(USER)
    assets = list_assets(USER, "personal")
    assert len(assets) == 1
    assert assets[0]["name"].startswith("Example: ")
    assert assets[0]["template_id"] is None  # blank, no template


def test_seed_contact(brain):
    from services.contacts_service import list_contacts

    svc.seed_contact(USER, "personal")
    contacts = list_contacts(USER, "personal")
    assert len(contacts) == 1
    assert contacts[0]["name"].startswith("Example: ")


def test_seed_finance_book(brain):
    from services.finance_service import list_books

    svc.seed_finance_book(USER)
    books = list_books(USER, "personal")
    assert len(books) == 1
    assert books[0]["name"].startswith("Example: ")
