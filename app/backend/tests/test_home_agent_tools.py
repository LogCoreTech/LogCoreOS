"""Tests for home_assistant's AI agent tools specifically — the real
module, not a fake one, since the interesting behavior here is the
module's own double gate (installed AND Home Assistant actually
configured) plus a real asymmetry in agent_service.py's hardcoded
tool-mode sets that this conversion had to preserve exactly (see
docs/MEMORY.md 2026-08-24). Tool names renamed 2026-08-24
(get_home_state -> get_home_assistant_state, control_home_device ->
control_home_assistant_device, trigger_home_automation ->
trigger_home_assistant_automation); activate_scene never said "home" and
stayed as-is."""

from unittest.mock import patch

from services import agent_service, ha_service, mod_store_service
from services.file_service import write_json

_HA_TOOL_NAMES = {
    "get_home_assistant_state",
    "control_home_assistant_device",
    "activate_scene",
    "trigger_home_assistant_automation",
}


def _user(name: str = "alice", disabled_modules: list[str] | None = None) -> dict:
    return {"name": name, "disabled_modules": disabled_modules or [], "role": "member"}


def _configure_ha(brain):
    write_json(brain / "_system" / "ha_config.json", {"url": "http://ha.local:8123", "token": "abc"})


def test_ha_tools_present_when_installed_and_configured(brain):
    mod_store_service.mark_installed("home_assistant", by="tester")
    _configure_ha(brain)

    names = {t["name"] for t in agent_service._get_tools(_user())}

    assert _HA_TOOL_NAMES <= names


def test_ha_tools_absent_when_installed_but_not_configured(brain):
    mod_store_service.mark_installed("home_assistant", by="tester")
    # deliberately no ha_config.json written

    names = {t["name"] for t in agent_service._get_tools(_user())}

    assert names.isdisjoint(_HA_TOOL_NAMES)


def test_ha_tools_absent_when_configured_but_not_installed(brain):
    _configure_ha(brain)
    # deliberately never installed — active_manifests() excludes it

    names = {t["name"] for t in agent_service._get_tools(_user())}

    assert names.isdisjoint(_HA_TOOL_NAMES)


def test_get_home_assistant_state_is_read_only_but_excluded_from_research_mode(brain):
    """A real, deliberate asymmetry predating this conversion:
    get_home_assistant_state is safe to run without approval (in
    _READ_TOOLS) but not offered in the narrower research mode
    (_RESEARCH_TOOLS) — preserved as a hardcoded name in agent_service.py
    rather than going through the generic read_only_agent_tools manifest
    union, which would incorrectly add it to both sets uniformly."""
    assert "get_home_assistant_state" in agent_service._READ_TOOLS
    assert "get_home_assistant_state" not in agent_service._RESEARCH_TOOLS


def test_control_home_assistant_device_requires_approval():
    """The other 3 HA tools are real write/action tools — never read-only,
    matching this codebase's "new tools are write-gated by default" rule."""
    assert "control_home_assistant_device" not in agent_service._READ_TOOLS
    assert "activate_scene" not in agent_service._READ_TOOLS
    assert "trigger_home_assistant_automation" not in agent_service._READ_TOOLS


def test_execute_tool_dispatches_get_home_assistant_state_through_to_ha_service(brain):
    mod_store_service.mark_installed("home_assistant", by="tester")
    _configure_ha(brain)

    with patch.object(ha_service, "get_state", return_value={"entity_id": "light.x", "state": "on"}) as mock_get:
        result = agent_service._execute_tool(
            "get_home_assistant_state", {"entity_ids": ["light.x"]}, _user()
        )

    mock_get.assert_called_once_with("light.x")
    assert result == [{"entity_id": "light.x", "state": "on"}]
