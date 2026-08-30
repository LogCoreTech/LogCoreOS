"""End-to-end verification that a real upgrading instance (one that existed
before ANY of the 14 converted modules were optional) ends up with every
formerly-always-on module correctly marked installed after a single
run_pending() pass — and that a genuinely fresh install correctly leaves
every optional module NOT installed while the 3 locked ones still are.

This is deliberately broader than any single module's own conversion test:
each module's own m0XX test proves ITS OWN guard logic works in isolation:
this file proves the full chain works together on one shared brain,
the way a real production upgrade actually runs it — all 31 core+module
migrations, in the same run, against the same files, once.

Goals (2026-08-28) joined _OPTIONAL alongside the 13-module Mod Store
rollout's own modules — it wasn't part of that rollout (it's a genuinely
new module, not a conversion of an already-existing router/service), but
it follows the exact same fresh-vs-upgrade guard idiom (features.json
existence) as every other optional module here, so it belongs in the same
set, not a separate one."""

from migrations.runner import run_pending
from services import mod_store_service

_LOCKED = {"tasks", "chat", "dashboard"}
_OPTIONAL = {
    "journal",
    "home_assistant",
    "automations",
    "calendar",
    "household",
    "team",
    "notes",
    "assets",
    "contacts",
    "finance",
    "goals",
}
_ALL_14 = _LOCKED | _OPTIONAL


def _seed_pre_existing_instance(brain):
    """Recreate the on-disk state of a real instance that existed before
    ANY of these 14 modules were ever optional — the exact condition each
    module's own upgrade migration keys off of."""
    from services.file_service import write_json

    (brain / "_system").mkdir(parents=True, exist_ok=True)
    # The one signal nearly every optional module's own m0XX guards on.
    write_json(brain / "_system" / "features.json", {"profile": "personal", "roles": {}})
    # home_assistant's own m016 guards on this specific file instead.
    write_json(brain / "_system" / "ha_config.json", {"url": "http://ha.local", "token": "tok"})


def test_upgrading_instance_ends_with_all_14_modules_installed(brain):
    _seed_pre_existing_instance(brain)

    applied = run_pending(brain)

    assert applied > 0
    still_missing = {m for m in _ALL_14 if not mod_store_service.is_installed(m)}
    assert not still_missing, f"modules never got marked installed on upgrade: {still_missing}"


def test_fresh_install_leaves_optional_modules_uninstalled(brain):
    # No features.json, no ha_config.json — a genuinely brand-new instance.
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    still_optional_but_installed = {m for m in _OPTIONAL if mod_store_service.is_installed(m)}
    assert not still_optional_but_installed, (
        f"optional modules incorrectly auto-installed on a fresh instance: "
        f"{still_optional_but_installed}"
    )
    still_locked_but_missing = {m for m in _LOCKED if not mod_store_service.is_installed(m)}
    assert not still_locked_but_missing, (
        f"locked modules must always install regardless of fresh-vs-upgrade: "
        f"{still_locked_but_missing}"
    )


def test_running_migrations_twice_is_idempotent(brain):
    _seed_pre_existing_instance(brain)

    first = run_pending(brain)
    second = run_pending(brain)

    assert first > 0
    assert second == 0, "a second run_pending() pass re-applied migrations that were already done"
    assert all(mod_store_service.is_installed(m) for m in _ALL_14)


def test_no_migration_name_collisions_across_all_14_modules(brain):
    """The boot-time collision check (module_registry.py) must find zero
    collisions among the 14 real, shipped modules — this is the actual
    production migration namespace, not a synthetic fixture."""
    from module_registry import discover_manifests

    manifests, errors = discover_manifests()

    collision_errors = {mid: msg for mid, msg in errors.items() if "collision" in msg}
    assert not collision_errors, f"real migration name collisions found: {collision_errors}"
    assert _ALL_14.issubset(
        manifests.keys()
    ), f"expected all 14 modules discoverable, missing: {_ALL_14 - manifests.keys()}"
