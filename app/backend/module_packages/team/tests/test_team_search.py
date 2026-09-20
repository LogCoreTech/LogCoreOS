"""Tests for team/manifest.py's own SearchProviderSpec resolvers.

Same bug as household's `_search_household_events` (see
module_packages/household/tests/test_household_search.py's docstring),
copy-pasted into `_search_team_events` too: matched every event's
`own_tags` against a hardcoded `[]` instead of the event's actual `tags`
field, so a tag-only search (Homes' `GET /homes/{id}/items`) could never
match a tagged team event."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.team.backend.router import add_team_event
from module_packages.team.manifest import _search_team_events
from routers._event_models import EventCreate


@pytest.fixture()
def member(brain):
    from services import auth_service

    return auth_service.create_user("bob@example.com", "password123", "Bob")


def test_team_event_matched_by_its_own_tag(member):
    add_team_event(
        EventCreate(title="Sprint planning", start_date="2026-09-01", tags=["home:cabin-ab12"]),
        member,
    )

    results = _search_team_events("", ["home:cabin-ab12"], member, "business")

    assert len(results) == 1
    assert results[0]["title"] == "Sprint planning"
    assert results[0]["tags"] == ["home:cabin-ab12"]


def test_team_event_not_matched_by_unrelated_tag(member):
    add_team_event(
        EventCreate(title="Sprint planning", start_date="2026-09-01", tags=["home:cabin-ab12"]),
        member,
    )

    assert _search_team_events("", ["home:other-cd34"], member, "business") == []
