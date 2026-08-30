"""Tests for the app-wide search fan-out (services/search_service.py) and
its registry discovery half (module_registry.search_providers()) —
Increment 1 of the app-wide search bar (docs/TASKS.md). Mirrors
test_goals_module_conversion.py's own style for provider-discovery tests
(mark_installed + real service calls, not mocks — this is a real
importlib-based discovery path)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import auth_service, mod_store_service, task_service

USER = "SearchUser"


@pytest.fixture()
def user_brain(brain):
    (brain / "USERS" / USER / "Tasks").mkdir(parents=True, exist_ok=True)
    auth_service.create_user("search@example.com", "password123", USER)
    mod_store_service.mark_installed("tasks", by="test")
    mod_store_service.mark_installed("goals", by="test")
    return brain


def _user(disabled_modules=None):
    return {"name": USER, "disabled_modules": disabled_modules or []}


def test_search_providers_discovers_tasks_and_goals(user_brain):
    from module_registry import search_providers

    providers = search_providers()
    assert "tasks:tasks" in providers
    assert "goals:goals" in providers


def test_search_provider_absent_when_owning_module_not_installed(brain):
    from module_registry import search_providers

    # Tasks is locked (uninstallable=True) — the `brain` fixture always
    # marks it installed, matching real boot behavior, so only Goals (an
    # ordinary optional module) is meaningfully absent here.
    providers = search_providers()
    assert "goals:goals" not in providers


def test_empty_query_and_empty_tags_returns_nothing(user_brain):
    from services import search_service

    assert search_service.search("", [], _user(), "personal") == []


def test_search_finds_matching_task_by_title(user_brain):
    from services import search_service

    task_service.add_task(USER, {"title": "Renew passport", "category": "Errands"})
    task_service.add_task(USER, {"title": "Buy groceries", "category": "Errands"})

    results = search_service.search("passport", [], _user(), "personal")
    titles = [r["title"] for r in results]
    assert "Renew passport" in titles
    assert "Buy groceries" not in titles
    assert results[0]["_module"] == "tasks"


def test_search_respects_disabled_modules(user_brain):
    from services import search_service

    task_service.add_task(USER, {"title": "Renew passport", "category": "Errands"})

    results = search_service.search("passport", [], _user(disabled_modules=["tasks"]), "personal")
    assert results == []


def test_search_filters_by_tag(user_brain):
    from services import search_service

    task_service.add_task(USER, {"title": "Renew passport", "category": "Errands", "tags": ["urgent"]})
    task_service.add_task(USER, {"title": "Buy groceries", "category": "Errands", "tags": ["routine"]})

    results = search_service.search("", ["urgent"], _user(), "personal")
    titles = [r["title"] for r in results]
    assert titles == ["Renew passport"]


@pytest.fixture()
def pool_brain(user_brain):
    mod_store_service.mark_installed("household", by="test")
    mod_store_service.mark_installed("team", by="test")
    return user_brain


def test_household_providers_discovered_when_installed(pool_brain):
    from module_registry import search_providers

    providers = search_providers()
    assert "household:tasks" in providers
    assert "household:goals" in providers
    assert "household:events" in providers
    assert "team:tasks" in providers
    assert "team:goals" in providers
    assert "team:events" in providers


def test_search_finds_household_pool_task(pool_brain):
    from services import search_service, task_service

    task_service.add_task("_household", {"title": "Buy groceries", "category": "Home"})

    results = search_service.search("groceries", [], _user(), "personal")
    assert any(r["title"] == "Buy groceries" and r["_module"] == "household" for r in results)


def test_search_respects_disabled_household_module(pool_brain):
    from services import search_service, task_service

    task_service.add_task("_household", {"title": "Buy groceries", "category": "Home"})

    # Household disabled for this user, but Tasks/Goals stay enabled.
    results = search_service.search("groceries", [], _user(disabled_modules=["household"]), "personal")
    assert results == []

    # A personal task with the same word IS still found — only the pool
    # provider was skipped, not the caller's own Tasks provider.
    task_service.add_task(USER, {"title": "Buy groceries too", "category": "Home"})
    results = search_service.search("groceries", [], _user(disabled_modules=["household"]), "personal")
    titles = [r["title"] for r in results]
    assert "Buy groceries too" in titles
    assert "Buy groceries" not in titles


def test_household_and_personal_tasks_dont_leak_into_each_other(pool_brain):
    from services import search_service, task_service

    task_service.add_task("_household", {"title": "Household-only widget", "category": "Home"})
    task_service.add_task(USER, {"title": "Personal-only widget", "category": "Home"})

    results = search_service.search("widget", [], _user(), "personal")
    by_module = {r["title"]: r["_module"] for r in results}
    assert by_module["Household-only widget"] == "household"
    assert by_module["Personal-only widget"] == "tasks"


def test_contacts_provider_finds_matching_contact(user_brain):
    from services import contacts_service, search_service

    mod_store_service.mark_installed("contacts", by="test")
    contacts_service.create_contact(USER, "personal", {"name": "Jane Doe", "notes": "met at conference"}, created_by=USER)

    results = search_service.search("conference", [], _user(), "personal")
    assert any(r["title"] == "Jane Doe" and r["_module"] == "contacts" for r in results)


def test_assets_provider_finds_matching_asset(user_brain):
    from services import assets_service, search_service

    mod_store_service.mark_installed("assets", by="test")
    assets_service.create_asset(USER, {"name": "Backup Generator", "notes": "propane fueled"}, created_by=USER)

    results = search_service.search("propane", [], _user(), "personal")
    assert any(r["title"] == "Backup Generator" and r["_module"] == "assets" for r in results)


def test_calendar_provider_finds_matching_event(user_brain):
    from services import events_service, search_service

    mod_store_service.mark_installed("calendar", by="test")
    events_service.add_event(
        USER, {"title": "Dentist appointment", "start_date": "2026-09-01", "notes": "annual checkup"}
    )

    results = search_service.search("checkup", [], _user(), "personal")
    assert any(r["title"] == "Dentist appointment" and r["_module"] == "calendar" for r in results)


def test_finance_provider_finds_matching_transaction_and_returns_book_id(user_brain):
    from services import finance_service, search_service

    mod_store_service.mark_installed("finance", by="test")
    book = finance_service.create_book(USER, "personal", name="Household", created_by=USER)
    account = finance_service.add_account(
        USER, "personal", book["id"], {"name": "Checking", "type": "checking", "opening_balance_cents": 0}
    )
    finance_service.add_transaction(
        USER, "personal", book,
        {"date": "2026-07-01", "amount_cents": -500, "account_id": account["id"], "payee": "Plumber Bob"},
        USER,
    )

    results = search_service.search("plumber", [], _user(), "personal")
    assert any(r["title"] == "Plumber Bob" and r["_module"] == "finance" and r["record_id"] == book["id"] for r in results)


def test_notes_provider_finds_matching_note_content(user_brain):
    from services import notes_service, search_service

    mod_store_service.mark_installed("notes", by="test")
    notes_service.create_note(USER, "trip-plan", "we're renting a canoe for the lake trip")

    results = search_service.search("canoe", [], _user(), "personal")
    assert any(r["title"] == "trip-plan" and r["_module"] == "notes" and r["record_id"] == "trip-plan" for r in results)


def test_journal_provider_finds_matching_entry_content(user_brain):
    from module_packages.journal.backend import service as journal_service
    from services import search_service

    mod_store_service.mark_installed("journal", by="test")
    journal_service.upsert_entry(USER, "2026-06-01", "went kayaking on the lake today")

    results = search_service.search("kayaking", [], _user(), "personal")
    assert any(r["title"] == "2026-06-01" and r["_module"] == "journal" and r["record_id"] == "2026-06-01" for r in results)


def test_broken_provider_degrades_to_no_results_without_crashing(user_brain, monkeypatch):
    from services import search_service
    import module_registry
    from module_registry import SearchProviderSpec

    def _boom(query, tags, user, workspace):
        raise RuntimeError("provider exploded")

    def _fake_search_providers():
        return {"tasks:tasks": SearchProviderSpec(key="tasks", label="Tasks", resolve=_boom)}

    monkeypatch.setattr(module_registry, "search_providers", _fake_search_providers)

    # Should not raise, just return no results from the broken provider.
    assert search_service.search("anything", [], _user(), "personal") == []
