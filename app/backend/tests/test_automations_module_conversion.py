"""Integration tests for automations' conversion into module_packages/
(increment — Automations, 2026-08-25) — not n8n_service's/inbox_service's
own business logic (covered by module_packages/automations/tests/
test_inbox_service.py and, for n8n_service itself, still an untested gap
predating this conversion, see docs/TESTING.md's Coverage Gaps), but the
surrounding machinery: the m019 upgrade migration (features.json-existence
guard, same idiom as journal's m015 — Automations was always-on before
this system existed, unlike Home Assistant's opt-in ha_config.json guard),
and a full install/uninstall/reinstall round-trip through the real Mod
Store service."""

from migrations.runner import run_pending
from services import mod_store_service


def test_m019_marks_automations_installed_on_upgrade(brain):
    """An existing instance (has _system/features.json from a prior setup)
    had automations permanently on — upgrading must not silently take the
    feature away."""
    (brain / "_system" / "features.json").write_text('{"profile": "personal", "roles": {}}')

    run_pending(brain)

    assert mod_store_service.is_installed("automations")


def test_m019_noop_on_fresh_install(brain):
    """No _system/features.json yet means this Brain never went through the
    always-on-automations era — it should start with automations NOT
    installed, matching the actual goal of slimming the default install."""
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("automations")


def test_install_uninstall_reinstall_round_trip_preserves_data(brain):
    """The real end-to-end guarantee: uninstalling automations never
    touches its data, and reinstalling picks it back up immediately."""
    from module_packages.automations.backend import inbox_service

    inbox_service.create_inbox("dana", "My Alerts", workflows=["price-watch"])

    mod_store_service.mark_installed("automations", by="tester")
    assert mod_store_service.is_installed("automations")

    mod_store_service.mark_uninstalled("automations", by="tester")
    assert not mod_store_service.is_installed("automations")
    # data untouched even while "uninstalled"
    assert inbox_service.load_store("dana")["inboxes"][0]["name"] == "My Alerts"

    mod_store_service.mark_installed("automations", by="tester")
    assert mod_store_service.is_installed("automations")
    assert inbox_service.load_store("dana")["inboxes"][0]["name"] == "My Alerts"
