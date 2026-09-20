"""Tests for household/manifest.py's own SearchProviderSpec resolvers.

Real bug found live 2026-09-18: `_search_household_events` matched every
event's `own_tags` against a hardcoded `[]` instead of the event's actual
`tags` field (copy-paste drift from `_search_household_tasks`/
`_search_household_goals`, which both did this correctly). A household
event tagged with a Homes module tag would carry the tag, but a tag-only
search (as Homes' `GET /homes/{id}/items` performs) could never match it —
reported by the owner as "when I tag events they don't show up on the
homes but have the tag." `_search_household_tasks`/`_search_household_goals`
never had this bug; no regression test needed for those."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.household.backend.router import add_household_event
from module_packages.household.manifest import _search_household_events
from routers._event_models import EventCreate


@pytest.fixture()
def member(brain):
    from services import auth_service

    return auth_service.create_user("alice@example.com", "password123", "Alice")


def test_household_event_matched_by_its_own_tag(member):
    add_household_event(
        EventCreate(title="Family dinner", start_date="2026-09-01", tags=["home:cabin-ab12"]),
        member,
    )

    results = _search_household_events("", ["home:cabin-ab12"], member, "personal")

    assert len(results) == 1
    assert results[0]["title"] == "Family dinner"
    assert results[0]["tags"] == ["home:cabin-ab12"]


def test_household_event_not_matched_by_unrelated_tag(member):
    add_household_event(
        EventCreate(title="Family dinner", start_date="2026-09-01", tags=["home:cabin-ab12"]),
        member,
    )

    assert _search_household_events("", ["home:other-cd34"], member, "personal") == []
