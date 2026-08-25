"""Home (Smart Home / Home Assistant) module manifest. See
module_registry.py for the ModuleManifest contract and docs/MEMORY.md's
2026-08-24 Home-conversion entry for the full design, including why
services/ha_service.py itself stays in core rather than moving here."""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.home.backend.router import router

    return router


def m016_backfill_home_installed_from_ha_config(brain: Path) -> None:
    """An instance that had already connected Home Assistant before this
    migration shipped (a real, persisted brain/_system/ha_config.json with a
    url+token) had Home effectively "on" already — mark it installed so
    upgrading never silently disconnects a working integration. An instance
    that never connected HA (no file, or one with a blank url/token) starts
    with Home correctly NOT installed — the actual goal (slimming the
    default install). Deliberately keyed on ha_config.json specifically,
    not a blanket "every pre-existing instance had it" assumption like
    journal's m015 — Home was already opt-in before this system existed."""
    config_file = brain / "_system" / "ha_config.json"
    if not config_file.exists():
        return  # never connected HA — Home correctly starts uninstalled

    from services import mod_store_service
    from services.file_service import brain_path, read_json

    if brain != brain_path():
        return  # test/alternate brain root — mod_store_service always reads the live one

    cfg = read_json(config_file, default={})
    if not (cfg.get("url") and cfg.get("token")):
        return  # file exists but incomplete — never actually connected

    mod_store_service.mark_installed("home", by="migration:m016")


MODULE = ModuleManifest(
    id="home",
    display_name="Smart Home",
    description="Control and monitor Home Assistant devices, scenes, and automations.",
    icon="💡",  # matches constants.js's existing nav icon
    version="1.0.0",
    router_prefix="/api/v1/home",
    router_tags=["home"],
    get_router=_get_router,
    owned_brain_paths=["Home"],
    owned_agent_tools=[
        "get_home_state",
        "control_home_device",
        "activate_scene",
        "trigger_home_automation",
    ],
    # get_home_state is read-only but deliberately NOT listed here — see
    # agent_tools.py's module docstring for why it stays a hardcoded name in
    # agent_service.py's _READ_TOOLS instead of going through this generic
    # union, which would also (incorrectly) add it to _RESEARCH_TOOLS.
    read_only_agent_tools=[],
    owned_block_types=["home_favourites"],
    migrations=[
        ("home:m016_backfill_home_installed_from_ha_config", m016_backfill_home_installed_from_ha_config),
    ],
    help_section={
        "id": "home",
        "icon": "🏡",
        "title": "Smart Home",
        "blurb": "Control your Home Assistant devices from LogCore — lights, switches, sensors, climate, scenes, and automations.",
        "howto": [
            "An admin connects your Home Assistant URL and token in Admin → Household.",
            "Browse entities by domain and toggle or adjust them from the tiles.",
            "Activate scenes or trigger HA automations from their panels.",
            "Star your favourites to pin them to the Dashboard widget for quick access.",
        ],
        "tips": [
            "You can also ask the AI to \"turn off the living room lights\" once Home Assistant is connected.",
            "Smart Home is personal-workspace only.",
        ],
        "modules": ["home"],
    },
)
