"""Integration tests for home_assistant's conversion into module_packages/
(increment 2 of the Mod Store rollout) — not ha_service's own client logic
(untested even before this conversion, see docs/TESTING.md's Coverage Gaps),
but the surrounding machinery: the m016 upgrade migration (deliberately
keyed on ha_config.json's own existence+completeness, not a blanket "every
pre-existing instance had it" assumption like journal's m015), the m017
id-rename migration and m018 block-type-rename migration (both added
2026-08-24 when the module id/Brain folder/dashboard-block-type were
renamed "home"-flavoured -> "home_assistant"-flavoured — carrying an
already-upgraded instance's real state across that rename), and a full
install/uninstall/reinstall round-trip through the real Mod Store service."""

from migrations.runner import run_pending
from services import mod_store_service
from services.file_service import (
    dashboard_templates_path,
    dashboards_path,
    global_dashboard_templates_path,
    read_json,
    write_json,
)


def test_m016_marks_home_assistant_installed_when_ha_was_already_configured(brain):
    """An existing instance that had already connected Home Assistant (a
    real url+token saved) had the feature effectively on — upgrading must
    not silently disconnect it."""
    write_json(brain / "_system" / "ha_config.json", {"url": "http://ha.local:8123", "token": "abc123"})

    run_pending(brain)

    assert mod_store_service.is_installed("home_assistant")


def test_m016_noop_on_fresh_install(brain):
    """No ha_config.json at all means this Brain never connected Home
    Assistant — it should start with home_assistant NOT installed, matching
    the actual goal of slimming the default install."""
    assert not (brain / "_system" / "ha_config.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("home_assistant")


def test_m016_noop_when_ha_config_file_exists_but_incomplete(brain):
    """A file that exists but never actually got a real url+token (e.g. an
    admin opened the form and saved a blank/partial one) doesn't count as
    "was using this feature" — home_assistant stays uninstalled."""
    write_json(brain / "_system" / "ha_config.json", {"url": "", "token": ""})

    run_pending(brain)

    assert not mod_store_service.is_installed("home_assistant")


def test_m017_renames_installed_modules_key(brain):
    """A real instance that installed under the old "home" id before the
    2026-08-24 rename must not look freshly-uninstalled after upgrading."""
    write_json(brain / "_system" / "installed_modules.json", {
        "installed": {"home": {"installed_at": "2026-08-01T00:00:00Z", "installed_by": "alice"}}
    })

    run_pending(brain)

    assert mod_store_service.is_installed("home_assistant")
    data = read_json(brain / "_system" / "installed_modules.json")
    assert "home" not in data["installed"]
    assert data["installed"]["home_assistant"]["installed_by"] == "alice"


def test_m017_renames_features_role_map_key(brain):
    """An admin who explicitly disabled Home Assistant for a role (e.g.
    cleaner) before the rename must not have that override silently
    dropped — dropping it would default the role back to enabled."""
    write_json(brain / "_system" / "features.json", {
        "profile": "personal",
        "roles": {"member": {"home": True}, "cleaner": {"home": False}},
    })

    run_pending(brain)

    data = read_json(brain / "_system" / "features.json")
    assert data["roles"]["cleaner"]["home_assistant"] is False
    assert "home" not in data["roles"]["cleaner"]
    assert "home" not in data["roles"]["member"]


def test_m017_renames_per_user_disabled_modules_list(brain):
    """A user's own explicit disabled_modules override (flat list form)
    must carry the rename too, or their opt-out silently reverts."""
    write_json(brain / "_system" / "auth.json", {
        "users": [{"id": "u1", "name": "Alice", "email": "a@x.com", "disabled_modules": ["home", "chat"]}]
    })

    run_pending(brain)

    data = read_json(brain / "_system" / "auth.json")
    assert data["users"][0]["disabled_modules"] == ["home_assistant", "chat"]


def test_m017_renames_per_user_disabled_modules_workspace_dict(brain):
    """Same as the flat-list case, but for the workspace-keyed dict form of
    disabled_modules (per get_effective_disabled()'s documented shapes)."""
    write_json(brain / "_system" / "auth.json", {
        "users": [{
            "id": "u1", "name": "Alice", "email": "a@x.com",
            "disabled_modules": {"personal": ["home"], "business": []},
        }]
    })

    run_pending(brain)

    data = read_json(brain / "_system" / "auth.json")
    assert data["users"][0]["disabled_modules"] == {"personal": ["home_assistant"], "business": []}


def test_m017_renames_real_brain_folder(brain):
    """The actual on-disk favourites file must move with the folder rename
    — get_favourites()/save_favourites() only ever look under the new name
    afterward, so a stale old folder would make existing favourites vanish."""
    favs_file = brain / "USERS" / "alice" / "Home" / "favourites.json"
    favs_file.parent.mkdir(parents=True)
    write_json(favs_file, {"entity_ids": ["light.kitchen"]})

    run_pending(brain)

    assert not (brain / "USERS" / "alice" / "Home").exists()
    moved = read_json(brain / "USERS" / "alice" / "HomeAssistant" / "favourites.json")
    assert moved["entity_ids"] == ["light.kitchen"]


def test_m017_is_idempotent_and_safe_on_a_fresh_instance(brain):
    """No old "home" state anywhere (a genuinely fresh instance) — m017 must
    be a clean no-op, and running the whole migration pass twice must not
    error or duplicate anything."""
    run_pending(brain)
    run_pending(brain)  # migrations.json already marks it applied; must not re-run or error

    assert not mod_store_service.is_installed("home_assistant")


def _block(type_: str, block_id: str = "b1") -> dict:
    return {"id": block_id, "type": type_, "config": {}, "layout": {"lg": {"x": 0, "y": 0, "w": 6, "h": 3}}}


def test_m018_renames_block_type_on_a_real_users_dashboard(brain):
    """The exact scenario this migration exists for: a real user already
    added the old "Smart Home Favourites" block to a real dashboard before
    the rename — it must keep resolving, not silently break, on upgrade."""
    from services import auth_service

    auth_service.create_user("alice@example.com", "password123", "alice")
    write_json(dashboards_path("alice"), {
        "dashboards": [{"id": "d1", "name": "Home", "blocks": [_block("home_favourites")]}]
    })

    run_pending(brain)

    data = read_json(dashboards_path("alice"))
    assert data["dashboards"][0]["blocks"][0]["type"] == "home_assistant_favourites"


def test_m018_renames_block_type_on_a_pool_dashboard(brain):
    """dashboards_service._all_stores() covers _household/_team too — a
    migration that only swept real per-user stores would miss pool
    dashboards entirely, same gap m011's own docstring calls out."""
    write_json(dashboards_path("_household"), {
        "dashboards": [{"id": "d1", "name": "Household", "blocks": [_block("home_favourites")]}]
    })

    run_pending(brain)

    data = read_json(dashboards_path("_household"))
    assert data["dashboards"][0]["blocks"][0]["type"] == "home_assistant_favourites"


def test_m018_leaves_unrelated_block_types_untouched(brain):
    from services import auth_service

    auth_service.create_user("alice@example.com", "password123", "alice")
    write_json(dashboards_path("alice"), {
        "dashboards": [{"id": "d1", "name": "Home", "blocks": [_block("top3_tasks", "b1"), _block("home_favourites", "b2")]}]
    })

    run_pending(brain)

    blocks = read_json(dashboards_path("alice"))["dashboards"][0]["blocks"]
    assert blocks[0]["type"] == "top3_tasks"
    assert blocks[1]["type"] == "home_assistant_favourites"


def test_m018_renames_block_type_in_a_per_user_template(brain):
    from services import auth_service

    auth_service.create_user("alice@example.com", "password123", "alice")
    write_json(dashboard_templates_path("alice"), {
        "templates": [{"id": "t1", "name": "My Template", "blocks": [_block("home_favourites")]}]
    })

    run_pending(brain)

    data = read_json(dashboard_templates_path("alice"))
    assert data["templates"][0]["blocks"][0]["type"] == "home_assistant_favourites"


def test_m018_renames_block_type_in_the_global_template(brain):
    write_json(global_dashboard_templates_path(), {
        "templates": [{"id": "t1", "name": "Global Template", "blocks": [_block("home_favourites")]}]
    })

    run_pending(brain)

    data = read_json(global_dashboard_templates_path())
    assert data["templates"][0]["blocks"][0]["type"] == "home_assistant_favourites"


def test_m018_is_idempotent_on_a_fresh_instance(brain):
    run_pending(brain)
    run_pending(brain)  # must not error with nothing to migrate

    assert not dashboards_path("alice").exists()


def test_install_uninstall_reinstall_round_trip_preserves_favourites(brain):
    """The real end-to-end guarantee: uninstalling home_assistant never
    touches its data, and reinstalling picks it back up immediately."""
    from services import ha_service

    ha_service.save_favourites("dana", ["light.living_room", "switch.porch"])

    mod_store_service.mark_installed("home_assistant", by="tester")
    assert mod_store_service.is_installed("home_assistant")

    mod_store_service.mark_uninstalled("home_assistant", by="tester")
    assert not mod_store_service.is_installed("home_assistant")
    # data untouched even while "uninstalled"
    assert ha_service.get_favourites("dana") == ["light.living_room", "switch.porch"]

    mod_store_service.mark_installed("home_assistant", by="tester")
    assert mod_store_service.is_installed("home_assistant")
    assert ha_service.get_favourites("dana") == ["light.living_room", "switch.porch"]
