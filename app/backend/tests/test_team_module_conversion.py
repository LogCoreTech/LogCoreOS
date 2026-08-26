"""Integration tests for team's conversion into module_packages/ (increment
— Household+Team, 2026-08-25). Mirrors test_household_module_conversion.py's
own shape — same reasoning throughout. Team declares no m023-equivalent of
its own: household's own m023 migration renames pool_tasks -> team_tasks
for business-workspace dashboards too, in the same pass — see
test_household_module_conversion.py's m023 tests for that coverage."""

from migrations.runner import run_pending
from services import mod_store_service


def test_m024_marks_team_installed_on_upgrade(brain):
    (brain / "_system" / "features.json").write_text('{"profile": "business", "roles": {}}')

    run_pending(brain)

    assert mod_store_service.is_installed("team")


def test_m024_noop_on_fresh_install(brain):
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("team")


def test_install_uninstall_reinstall_round_trip_preserves_data(brain):
    from services import task_service

    task_service.add_task("_team", {"title": "Ship it", "category": "Work"})

    mod_store_service.mark_installed("team", by="tester")
    assert mod_store_service.is_installed("team")

    mod_store_service.mark_uninstalled("team", by="tester")
    assert not mod_store_service.is_installed("team")
    assert task_service.list_tasks("_team")[0]["title"] == "Ship it"

    mod_store_service.mark_installed("team", by="tester")
    assert mod_store_service.is_installed("team")
    assert task_service.list_tasks("_team")[0]["title"] == "Ship it"
