"""Home Assistant module manifest. See module_registry.py for the
ModuleManifest contract and docs/MEMORY.md's 2026-08-24 entries for the
full design, including why services/ha_service.py itself stays in core
rather than moving here, why the admin config form lives on Admin →
Hosting rather than a dedicated Home Assistant admin page, and why the
module id/directory/Brain folder were renamed from "home"/"Home" to
"home_assistant"/"HomeAssistant" (m017 below carries existing installs'
state across that rename) while the frontend route (`/home`), the help
section's own anchor id, the AI tool names, and the `home_favourites`
dashboard block type were deliberately left unchanged — none of those are
"the module's id," they're independent, already-accurate identifiers of
their own that renaming would only add risk to for zero real benefit."""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.home_assistant.backend.router import router

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
    journal's m015 — Home was already opt-in before this system existed.

    Migration key deliberately kept as "home:..." (not renamed to
    "home_assistant:...") even after the 2026-08-24 id rename below — a
    migration's tracking key only needs to be a unique string, never needs
    to match the module's current id (confirmed: module_registry.py's
    collision check only checks uniqueness), and renaming it would make an
    already-applied migration look unapplied on any instance that already
    booted with this code, causing it to silently re-run and potentially
    re-install a module the admin had explicitly uninstalled since."""
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

    mod_store_service.mark_installed("home_assistant", by="migration:m016")


def m017_rename_home_id_to_home_assistant(brain: Path) -> None:
    """One-time carry-forward for the 2026-08-24 id rename ("home" ->
    "home_assistant", brain folder "Home" -> "HomeAssistant") — without this,
    any instance that already installed/configured/disabled the old id would
    look freshly-uninstalled after upgrading to this code, and any user's
    favourites would appear to vanish (still on disk, just under the old
    folder name `get_favourites()`/`save_favourites()` no longer look in).
    Every step below is independently idempotent (checks before acting), so
    a partial prior run or a fresh install (nothing to migrate) are both safe
    no-ops."""
    from services.file_service import read_json, write_json

    # 1. installed_modules.json: rename the "installed" dict's key.
    installed_file = brain / "_system" / "installed_modules.json"
    if installed_file.exists():
        data = read_json(installed_file, default={"installed": {}})
        installed = data.get("installed", {})
        if "home" in installed and "home_assistant" not in installed:
            installed["home_assistant"] = installed.pop("home")
            write_json(installed_file, data)

    # 2. features.json: rename the "home" key in every role's module map.
    features_file = brain / "_system" / "features.json"
    if features_file.exists():
        data = read_json(features_file, default={})
        roles = data.get("roles") or {}
        changed = False
        for role_map in roles.values():
            if "home" in role_map and "home_assistant" not in role_map:
                role_map["home_assistant"] = role_map.pop("home")
                changed = True
        if changed:
            write_json(features_file, data)

    # 3. auth.json: rename "home" -> "home_assistant" inside every user's
    # disabled_modules, which is either a flat list or a workspace-keyed dict.
    auth_file = brain / "_system" / "auth.json"
    if auth_file.exists():
        data = read_json(auth_file, default={"users": []})
        changed = False
        for user in data.get("users", []):
            dm = user.get("disabled_modules")
            if isinstance(dm, list):
                if "home" in dm and "home_assistant" not in dm:
                    user["disabled_modules"] = [
                        "home_assistant" if m == "home" else m for m in dm
                    ]
                    changed = True
            elif isinstance(dm, dict):
                for workspace, mods in dm.items():
                    if isinstance(mods, list) and "home" in mods and "home_assistant" not in mods:
                        dm[workspace] = [
                            "home_assistant" if m == "home" else m for m in mods
                        ]
                        changed = True
        if changed:
            write_json(auth_file, data)

    # 4. Real Brain folder rename, one real user at a time — Path.rename() is
    # a single atomic filesystem operation (same-volume, always true here),
    # never a copy-then-delete that could partially fail.
    users_dir = brain / "USERS"
    if users_dir.exists():
        for user_dir in users_dir.iterdir():
            if not user_dir.is_dir():
                continue
            old = user_dir / "Home"
            new = user_dir / "HomeAssistant"
            if old.is_dir() and not new.exists():
                old.rename(new)


MODULE = ModuleManifest(
    id="home_assistant",
    display_name="Home Assistant",
    description="Control and monitor Home Assistant devices, scenes, and automations.",
    icon="💡",  # matches constants.js's existing nav icon
    version="1.0.0",
    router_prefix="/api/v1/home_assistant",
    router_tags=["home_assistant"],
    get_router=_get_router,
    owned_brain_paths=["HomeAssistant"],
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
        ("home_assistant:m017_rename_home_id_to_home_assistant", m017_rename_home_id_to_home_assistant),
    ],
    help_section={
        "id": "home",
        "icon": "🏡",
        "title": "Home Assistant",
        "blurb": "Control your Home Assistant devices from LogCore — lights, switches, sensors, climate, scenes, and automations.",
        "howto": [
            "An admin connects your Home Assistant URL and token in Admin → Hosting.",
            "Browse entities by domain and toggle or adjust them from the tiles.",
            "Activate scenes or trigger HA automations from their panels.",
            "Star your favourites to pin them to the Dashboard widget for quick access.",
        ],
        "tips": [
            "You can also ask the AI to \"turn off the living room lights\" once Home Assistant is connected.",
            "Home Assistant is personal-workspace only.",
        ],
        "modules": ["home_assistant"],
    },
)
