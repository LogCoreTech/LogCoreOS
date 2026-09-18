"""Tests for the Home Assistant Favourites block —
module_packages/home_assistant/backend/dashboard_block.py's
resolve_home_assistant_favourites(), the first-ever coverage of this
resolver. It reuses services/ha_service.py as-is (per the module's own
docstring) rather than any new aggregation, so the HA HTTP call
(get_states) is mocked via unittest.mock.patch — no live Home Assistant
instance to hit in this environment — while get_favourites/is_configured
are exercised for real against the isolated `brain` fixture the same way
every other converted module's dashboard-block tests do."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.home_assistant.backend.dashboard_block import (
    resolve_home_assistant_favourites,
)
from services import auth_service, ha_service
from services.dashboard_blocks.registry import BlockRenderCtx


@pytest.fixture()
def users(brain):
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


def test_non_personal_workspace_locks_not_found(users):
    """This block is personal-workspace-only (workspace="personal" on its
    BlockSpec); the resolver enforces that itself as its very first check."""
    result = resolve_home_assistant_favourites(_ctx(workspace="team"))
    assert result.ok is False
    assert result.locked_reason == "not_found"


def test_owner_scope_locks_no_access_for_non_owner_viewer(users):
    """scope_configurable=True lets a dashboard config request scope="owner"
    — scoped_target() then only resolves for the viewer who IS that owner;
    anyone else viewing the same dashboard gets no_access."""
    result = resolve_home_assistant_favourites(
        _ctx(viewer="Bob", owner="Alice", config={"scope": "owner"})
    )
    assert result.ok is False
    assert result.locked_reason == "no_access"


def test_ha_not_configured_returns_ok_with_no_entities(users):
    with patch("services.ha_service.is_configured", return_value=False):
        result = resolve_home_assistant_favourites(_ctx())
    assert result.ok is True
    assert result.data == {"entities": []}


def test_favourites_empty_returns_ok_with_no_entities(users):
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.get_favourites", return_value=[]) as mock_favs:
            with patch("services.ha_service.get_states") as mock_states:
                result = resolve_home_assistant_favourites(_ctx())
    mock_favs.assert_called_once_with("Alice")
    mock_states.assert_not_called()
    assert result.ok is True
    assert result.data == {"entities": []}


def test_favourites_present_returns_only_matching_entities(users):
    states = [
        {"entity_id": "light.kitchen", "state": "on"},
        {"entity_id": "light.garage", "state": "off"},
        {"entity_id": "lock.front_door", "state": "locked"},
    ]
    with patch("services.ha_service.is_configured", return_value=True):
        with patch(
            "services.ha_service.get_favourites",
            return_value=["light.kitchen", "lock.front_door"],
        ):
            with patch("services.ha_service.get_states", return_value=states) as mock_states:
                result = resolve_home_assistant_favourites(_ctx())
    mock_states.assert_called_once_with()
    assert result.ok is True
    assert {e["entity_id"] for e in result.data["entities"]} == {
        "light.kitchen",
        "lock.front_door",
    }


def test_get_states_error_returns_ok_with_no_entities(users):
    """The resolver deliberately swallows any HA fetch failure (a dashboard
    block rendering should degrade to empty, not 502 the whole dashboard)."""
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.get_favourites", return_value=["light.kitchen"]):
            with patch("services.ha_service.get_states", side_effect=RuntimeError("boom")):
                result = resolve_home_assistant_favourites(_ctx())
    assert result.ok is True
    assert result.data == {"entities": []}


def test_favourites_scoped_to_the_correct_target_user(users):
    """scoped_target() defaults to the viewer themselves (no scope config)
    — favourites must be looked up for Bob, not Alice, when Bob is viewing
    his own personal dashboard."""
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.get_favourites", return_value=[]) as mock_favs:
            resolve_home_assistant_favourites(_ctx(viewer="Bob", owner="Bob"))
    mock_favs.assert_called_once_with("Bob")
