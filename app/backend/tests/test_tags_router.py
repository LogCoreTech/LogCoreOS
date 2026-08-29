"""Tests for routers/tags.py — mirrors routers/priorities.py's own shape
(login-required, no module gate)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from routers.tags import get_tags
from services import tags_service


@pytest.fixture()
def alice(brain):
    from services import auth_service

    user = auth_service.create_user("alice@example.com", "password123", "Alice")
    yield user
    auth_service._revoked_jtis.clear()


def test_get_tags_returns_personal_vocabulary(alice):
    tags_service.register_tags("Alice", "personal", ["urgent"])
    result = get_tags(False, alice, "personal")
    assert result == {"tags": ["urgent"]}


def test_get_tags_pool_returns_household_vocabulary(alice):
    tags_service.register_tags("_household", "personal", ["family-shared"])
    result = get_tags(True, alice, "personal")
    assert result == {"tags": ["family-shared"]}


def test_get_tags_pool_resolves_team_in_business_workspace(alice):
    tags_service.register_tags("_team", "personal", ["work-tag"])
    result = get_tags(True, alice, "business")
    assert result == {"tags": ["work-tag"]}


def test_get_tags_empty_by_default(alice):
    assert get_tags(False, alice, "personal") == {"tags": []}
