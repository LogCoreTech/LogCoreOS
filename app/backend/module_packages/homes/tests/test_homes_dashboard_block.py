"""Tests for the Home Health block (module_packages/homes/backend/
dashboard_block.py) — mirrors module_packages/finance/tests/
test_finance_dashboard_block.py's exact fixture/_ctx() shape.

Every date used is derived from date.today() (never a hardcoded literal
alongside a relative comparison) — see docs/MEMORY.md's 2026-09-17 Known
Gotchas entry on exactly this class of bug: the resolver's own overdue/
upcoming/amount-due-this-month logic all compares against "today", so a
test that hardcodes a date would silently drift out of range as real time
passes."""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.homes.backend import service as homes_service
from services import auth_service, events_service, finance_service, task_service
from services.dashboard_blocks.registry import BlockRenderCtx, _load_all_resolvers

_load_all_resolvers()

from module_packages.homes.backend.dashboard_block import resolve_home_health


@pytest.fixture()
def users(brain):
    from services import mod_store_service

    mod_store_service.mark_installed("homes", by="test-fixture")
    mod_store_service.mark_installed("household", by="test-fixture")
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def _ctx(viewer="Alice", config=None, workspace="personal", is_admin=False, owner="Alice"):
    return BlockRenderCtx(
        viewer=viewer,
        viewer_role="member",
        is_admin=is_admin,
        workspace=workspace,
        config=config or {},
        dashboard_owner=owner,
    )


def test_not_found_with_no_home_id(users):
    result = resolve_home_health(_ctx())
    assert result.ok is False
    assert result.locked_reason == "not_found"


def test_no_access_for_a_home_belonging_to_another_user(users):
    home = homes_service.create_home("Alice", {"name": "Alice's place", "ownership_type": "rent"})

    result = resolve_home_health(_ctx(viewer="Bob", config={"home_id": home["id"]}))

    assert result.ok is False
    assert result.locked_reason == "no_access"


def test_open_and_overdue_task_counts(users):
    home = homes_service.create_home("Alice", {"name": "Cabin", "ownership_type": "own"})
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    overdue = task_service.add_task(
        "Alice", {"title": "Overdue", "due_date": yesterday, "tags": [home["tag"]]}
    )
    task_service.add_task(
        "Alice", {"title": "Not due yet", "due_date": tomorrow, "tags": [home["tag"]]}
    )
    done = task_service.add_task(
        "Alice", {"title": "Finished", "due_date": yesterday, "tags": [home["tag"]]}
    )
    task_service.update_task("Alice", done["id"], {"status": "done"})
    # Untagged — must not count toward this home's stats.
    task_service.add_task("Alice", {"title": "Unrelated", "due_date": yesterday})

    result = resolve_home_health(_ctx(config={"home_id": home["id"]}))

    assert result.ok is True
    assert result.data["open_task_count"] == 2
    assert result.data["overdue_task_count"] == 1
    assert overdue["due_date"] == yesterday  # sanity on the fixture itself


def test_upcoming_event_count_excludes_past_events(users):
    home = homes_service.create_home("Alice", {"name": "Cabin", "ownership_type": "own"})
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    events_service.add_event(
        "Alice", {"title": "Past", "start_date": yesterday, "tags": [home["tag"]]}
    )
    events_service.add_event(
        "Alice", {"title": "Upcoming", "start_date": tomorrow, "tags": [home["tag"]]}
    )

    result = resolve_home_health(_ctx(config={"home_id": home["id"]}))

    assert result.data["upcoming_event_count"] == 1


def test_lease_end_passed_through_from_the_home_record(users):
    home = homes_service.create_home(
        "Alice",
        {"name": "Cabin", "ownership_type": "rent", "rent": {"lease_end": "2027-01-01"}},
    )

    result = resolve_home_health(_ctx(config={"home_id": home["id"]}))

    assert result.data["lease_end"] == "2027-01-01"
    assert result.data["ownership_type"] == "rent"


def test_amount_due_this_month_sums_tagged_expenses_only(users):
    home = homes_service.create_home("Alice", {"name": "Cabin", "ownership_type": "own"})
    book = finance_service.create_book("Alice", "personal", name="Ledger", created_by="Alice")
    account = finance_service.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking"}
    )
    today_iso = date.today().isoformat()
    finance_service.add_transaction(
        "Alice",
        "personal",
        book,
        {
            "date": today_iso,
            "amount_cents": -5000,
            "account_id": account["id"],
            "tags": [home["tag"]],
        },
        created_by="Alice",
    )
    # Income (positive) — must not count toward "amount due."
    finance_service.add_transaction(
        "Alice",
        "personal",
        book,
        {
            "date": today_iso,
            "amount_cents": 2000,
            "account_id": account["id"],
            "tags": [home["tag"]],
        },
        created_by="Alice",
    )
    # Untagged expense — must not count either.
    finance_service.add_transaction(
        "Alice",
        "personal",
        book,
        {"date": today_iso, "amount_cents": -999, "account_id": account["id"]},
        created_by="Alice",
    )

    result = resolve_home_health(_ctx(config={"home_id": home["id"]}))

    assert result.data["amount_due_cents"] == 5000


def test_pool_home_end_to_end(users):
    home = homes_service.create_home(
        "Alice", {"name": "Shared house", "ownership_type": "own"}, workspace="personal"
    )
    converted = homes_service.convert_to_pool("Alice", home["id"], "personal", "_household")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    task_service.add_task(
        "_household", {"title": "Mow the lawn", "due_date": yesterday, "tags": [converted["tag"]]}
    )

    # Bob (a different household member) viewing his own dashboard block.
    result = resolve_home_health(_ctx(viewer="Bob", config={"home_id": converted["id"]}))

    assert result.ok is True
    assert result.data["open_task_count"] == 1
    assert result.data["overdue_task_count"] == 1
