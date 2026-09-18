"""Router-level tests for module_packages/home_assistant/backend/router.py —
the first-ever coverage of this router (agent_tools.py's own tool-calling
logic is already covered by tests/test_home_agent_tools.py, a core, not
module-nested, test file left alone by this conversion). services/
ha_service.py's HTTP-calling functions (get_state/get_states/call_service/
etc.) have no live Home Assistant instance to hit in this environment, so
every test here mocks them via unittest.mock.patch rather than making real
HTTP calls — this file is about the router's own body logic: the
not-configured short-circuits (empty list vs. 503), 502-wrapping of HA
errors, and the entity-id-derived service-domain allowlist in
call_entity_service (2026-09-16, closing the same crafted-entity_id gap
agent_tools.py's control_home_assistant_device tool closed).

Endpoint functions are called directly with a pre-resolved user dict,
matching this test suite's established convention (see
test_household_router.py/test_dashboard_router.py) — Depends(require_admin)/
Depends(_require_home) are bypassed for the endpoint-body tests the same way
every other module's router tests bypass them.

Unlike those other files, the admin gate and the module gate on GET /status
and POST /config get their own tests below, calling require_admin and the
router's own _require_home dependency directly (they're plain functions,
callable outside FastAPI's DI). That's a deliberate, narrow exception to the
"dependency chain is a pre-existing, untested gap" note other module router
test files carry (test_assets_router.py, test_household_router.py, etc.):
the module gate on these two endpoints is this session's own S22 fix, not
old, un-scoped-to-touch code, so it gets verified here rather than filed
under that same standing gap."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.home_assistant.backend.router import (
    CallServiceRequest,
    FavouritesRequest,
    HaConfigRequest,
    _require_home,
    activate_scene,
    call_entity_service,
    get_entity,
    get_favourites,
    ha_status,
    list_areas,
    list_entities,
    list_ha_automations,
    list_scenes,
    save_favourites,
    save_ha_config,
    trigger_ha_automation,
)
from routers.auth import require_admin


@pytest.fixture()
def users(brain):
    from services import auth_service

    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


# ── Gates on GET /status and POST /config ──────────────────────────────────
# Both endpoints declare Depends(require_admin) AND Depends(_require_home) —
# the module gate is this session's S22 fix, so both get exercised directly.


def test_require_admin_blocks_non_admin(users):
    with pytest.raises(HTTPException) as exc:
        require_admin(users["bob"])
    assert exc.value.status_code == 403


def test_require_admin_allows_admin(users):
    assert require_admin(users["alice"]) == users["alice"]


def test_require_home_blocks_when_module_disabled(users):
    bob = dict(users["bob"], disabled_modules=["home_assistant"])
    with pytest.raises(HTTPException) as exc:
        _require_home(bob)
    assert exc.value.status_code == 403


def test_require_home_allows_when_module_not_disabled(users):
    assert _require_home(users["bob"]) == users["bob"]


# ── GET /status, POST /config (body logic) ─────────────────────────────────


def test_status_returns_connection_test_result(users):
    with patch(
        "services.ha_service.test_connection",
        return_value={"ok": True, "url": "http://ha.local:8123"},
    ) as mock_test:
        result = ha_status(users["alice"])
    mock_test.assert_called_once_with()
    assert result == {"ok": True, "url": "http://ha.local:8123"}


def test_config_saves_stripped_url_and_token(users):
    with patch("services.ha_service.save_config") as mock_save:
        result = save_ha_config(
            HaConfigRequest(url="  http://ha.local:8123  ", token="  secret-token  "),
            users["alice"],
        )
    mock_save.assert_called_once_with({"url": "http://ha.local:8123", "token": "secret-token"})
    assert result == {"ok": True}


# ── GET /entities ────────────────────────────────────────────────────────────


def test_list_entities_returns_empty_when_not_configured(users):
    with patch("services.ha_service.is_configured", return_value=False):
        with patch("services.ha_service.get_states") as mock_states:
            result = list_entities(current_user=users["bob"])
    mock_states.assert_not_called()
    assert result == []


def test_list_entities_returns_states_when_configured(users):
    states = [{"entity_id": "light.kitchen", "state": "on"}]
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.get_states", return_value=states) as mock_states:
            result = list_entities(current_user=users["bob"])
    mock_states.assert_called_once_with(None)
    assert result == states


def test_list_entities_wraps_ha_error_as_502(users):
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.get_states", side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc:
                list_entities(current_user=users["bob"])
    assert exc.value.status_code == 502


# ── GET /entities/{entity_id} ────────────────────────────────────────────────


def test_get_entity_503_when_not_configured(users):
    with patch("services.ha_service.is_configured", return_value=False):
        with pytest.raises(HTTPException) as exc:
            get_entity("light.kitchen", users["bob"])
    assert exc.value.status_code == 503


def test_get_entity_returns_state_when_configured(users):
    state = {"entity_id": "light.kitchen", "state": "on"}
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.get_state", return_value=state) as mock_state:
            result = get_entity("light.kitchen", users["bob"])
    mock_state.assert_called_once_with("light.kitchen")
    assert result == state


def test_get_entity_wraps_ha_error_as_502(users):
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.get_state", side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc:
                get_entity("light.kitchen", users["bob"])
    assert exc.value.status_code == 502


# ── POST /entities/{entity_id}/call — domain allowlist ──────────────────────


def test_call_entity_service_503_when_not_configured(users):
    with patch("services.ha_service.is_configured", return_value=False):
        with pytest.raises(HTTPException) as exc:
            call_entity_service(
                "light.kitchen", CallServiceRequest(service="turn_on"), users["bob"]
            )
    assert exc.value.status_code == 503


def test_call_entity_service_blocks_disallowed_domain(users):
    """automation.trigger is exactly the crafted-entity_id case
    ha_service.ALLOWED_SERVICE_DOMAINS' docstring calls out — automation
    isn't in the allowlist, so a caller can't reach it by posting an
    automation.* entity_id through this endpoint (trigger_ha_automation
    below reaches the same HA service through its own hardcoded call, which
    the allowlist deliberately doesn't gate)."""
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.call_service") as mock_call:
            with pytest.raises(HTTPException) as exc:
                call_entity_service(
                    "automation.morning_routine",
                    CallServiceRequest(service="trigger"),
                    users["bob"],
                )
    assert exc.value.status_code == 403
    mock_call.assert_not_called()


def test_call_entity_service_allows_allowed_domain(users):
    with patch("services.ha_service.is_configured", return_value=True):
        with patch(
            "services.ha_service.call_service", return_value={"ok": True, "result": []}
        ) as mock_call:
            result = call_entity_service(
                "light.kitchen",
                CallServiceRequest(service="turn_on", data={"brightness": 200}),
                users["bob"],
            )
    mock_call.assert_called_once_with(
        "light", "turn_on", {"brightness": 200, "entity_id": "light.kitchen"}
    )
    assert result == {"ok": True, "result": []}


def test_call_entity_service_wraps_ha_error_as_502(users):
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.call_service", side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc:
                call_entity_service(
                    "light.kitchen", CallServiceRequest(service="turn_on"), users["bob"]
                )
    assert exc.value.status_code == 502


# ── GET /areas ───────────────────────────────────────────────────────────────


def test_list_areas_returns_empty_when_not_configured(users):
    with patch("services.ha_service.is_configured", return_value=False):
        assert list_areas(current_user=users["bob"]) == []


def test_list_areas_returns_data_when_configured(users):
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.get_areas", return_value=["Kitchen", "Garage"]):
            assert list_areas(current_user=users["bob"]) == ["Kitchen", "Garage"]


# ── GET /scenes, POST /scenes/{id}/activate ─────────────────────────────────


def test_list_scenes_returns_empty_when_not_configured(users):
    with patch("services.ha_service.is_configured", return_value=False):
        assert list_scenes(current_user=users["bob"]) == []


def test_list_scenes_returns_data_when_configured(users):
    scenes = [{"entity_id": "scene.movie_night", "state": "scening"}]
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.get_scenes", return_value=scenes):
            assert list_scenes(current_user=users["bob"]) == scenes


def test_activate_scene_503_when_not_configured(users):
    with patch("services.ha_service.is_configured", return_value=False):
        with pytest.raises(HTTPException) as exc:
            activate_scene("scene.movie_night", users["bob"])
    assert exc.value.status_code == 503


def test_activate_scene_calls_scene_turn_on(users):
    with patch("services.ha_service.is_configured", return_value=True):
        with patch(
            "services.ha_service.call_service", return_value={"ok": True, "result": []}
        ) as mock_call:
            result = activate_scene("scene.movie_night", users["bob"])
    mock_call.assert_called_once_with("scene", "turn_on", {"entity_id": "scene.movie_night"})
    assert result == {"ok": True, "result": []}


# ── GET /automations, POST /automations/{id}/trigger ────────────────────────


def test_list_automations_returns_empty_when_not_configured(users):
    with patch("services.ha_service.is_configured", return_value=False):
        assert list_ha_automations(current_user=users["bob"]) == []


def test_list_automations_returns_data_when_configured(users):
    automations = [{"entity_id": "automation.morning_routine", "state": "on"}]
    with patch("services.ha_service.is_configured", return_value=True):
        with patch("services.ha_service.get_automations", return_value=automations):
            assert list_ha_automations(current_user=users["bob"]) == automations


def test_trigger_automation_503_when_not_configured(users):
    with patch("services.ha_service.is_configured", return_value=False):
        with pytest.raises(HTTPException) as exc:
            trigger_ha_automation("automation.morning_routine", users["bob"])
    assert exc.value.status_code == 503


def test_trigger_automation_calls_service(users):
    with patch("services.ha_service.is_configured", return_value=True):
        with patch(
            "services.ha_service.trigger_automation", return_value={"ok": True, "result": []}
        ) as mock_trigger:
            result = trigger_ha_automation("automation.morning_routine", users["bob"])
    mock_trigger.assert_called_once_with("automation.morning_routine")
    assert result == {"ok": True, "result": []}


# ── GET/PUT /favourites ──────────────────────────────────────────────────────


def test_get_favourites_returns_service_result_for_current_user(users):
    with patch("services.ha_service.get_favourites", return_value=["light.kitchen"]) as mock_get:
        result = get_favourites(users["bob"])
    mock_get.assert_called_once_with("Bob")
    assert result == ["light.kitchen"]


def test_save_favourites_persists_for_current_user(users):
    with patch("services.ha_service.save_favourites") as mock_save:
        result = save_favourites(
            FavouritesRequest(entity_ids=["light.kitchen", "lock.front"]), users["bob"]
        )
    mock_save.assert_called_once_with("Bob", ["light.kitchen", "lock.front"])
    assert result == {"ok": True}
