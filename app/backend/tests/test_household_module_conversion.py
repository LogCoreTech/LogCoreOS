"""Integration tests for household's conversion into module_packages/
(increment — Household+Team, 2026-08-25) — not the router's own CRUD logic
(covered by module_packages/household/tests/test_router.py) or
task_service/events_service (stay core, already covered elsewhere): the
m022 upgrade migration (features.json-existence guard, same idiom as
journal's m015/automations' m019/calendar's m020/tasks' — well, tasks'
m021 has no guard at all, since tasks is locked; household is optional, so
it needs one), a full install→uninstall→reinstall round-trip, and the m023
pool_tasks block-type-split migration (the real reason this needed its own
migration at all — a single shared block type that used to serve both
pools couldn't be gated to either module individually once both became
real, discoverable modules)."""

from migrations.runner import run_pending
from services import mod_store_service


def test_m022_marks_household_installed_on_upgrade(brain):
    (brain / "_system" / "features.json").write_text('{"profile": "personal", "roles": {}}')

    run_pending(brain)

    assert mod_store_service.is_installed("household")


def test_m022_noop_on_fresh_install(brain):
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("household")


def test_install_uninstall_reinstall_round_trip_preserves_data(brain):
    from services import task_service

    task_service.add_task("_household", {"title": "Dishes", "category": "Home"})

    mod_store_service.mark_installed("household", by="tester")
    assert mod_store_service.is_installed("household")

    mod_store_service.mark_uninstalled("household", by="tester")
    assert not mod_store_service.is_installed("household")
    assert task_service.list_tasks("_household")[0]["title"] == "Dishes"

    mod_store_service.mark_installed("household", by="tester")
    assert mod_store_service.is_installed("household")
    assert task_service.list_tasks("_household")[0]["title"] == "Dishes"


def test_m023_renames_pool_tasks_by_dashboard_workspace(brain):
    """A dashboard already carrying a pool_tasks block gets renamed based
    on THAT dashboard's own workspace — the real reason this couldn't be a
    flat 1:1 rename like home_assistant's m018."""
    from services import auth_service, dashboards_service
    from services.file_service import dashboards_path, read_json, write_json

    auth_service.create_user("alice@example.com", "password123", "Alice")

    personal_path = dashboards_path("Alice", "personal")
    write_json(
        personal_path,
        {
            "dashboards": [
                {
                    "id": "d1",
                    "owner": "Alice",
                    "blocks": [{"id": "b1", "type": "pool_tasks", "config": {}}],
                }
            ]
        },
    )
    business_path = dashboards_path("Alice", "business")
    write_json(
        business_path,
        {
            "dashboards": [
                {
                    "id": "d2",
                    "owner": "Alice",
                    "blocks": [{"id": "b2", "type": "pool_tasks", "config": {}}],
                }
            ]
        },
    )

    from module_packages.household.manifest import m023_rename_pool_tasks_block_type

    m023_rename_pool_tasks_block_type(brain)

    personal_data = read_json(personal_path, default={})
    business_data = read_json(business_path, default={})
    assert personal_data["dashboards"][0]["blocks"][0]["type"] == "household_tasks"
    assert business_data["dashboards"][0]["blocks"][0]["type"] == "team_tasks"


def test_m023_leaves_unrelated_block_types_untouched(brain):
    from services import auth_service
    from services.file_service import dashboards_path, read_json, write_json

    auth_service.create_user("alice@example.com", "password123", "Alice")
    path = dashboards_path("Alice", "personal")
    write_json(
        path,
        {
            "dashboards": [
                {
                    "id": "d1",
                    "owner": "Alice",
                    "blocks": [{"id": "b1", "type": "top3_tasks", "config": {}}],
                }
            ]
        },
    )

    from module_packages.household.manifest import m023_rename_pool_tasks_block_type

    m023_rename_pool_tasks_block_type(brain)

    data = read_json(path, default={})
    assert data["dashboards"][0]["blocks"][0]["type"] == "top3_tasks"


def test_m023_is_idempotent(brain):
    from services import auth_service
    from services.file_service import dashboards_path, read_json, write_json

    auth_service.create_user("alice@example.com", "password123", "Alice")
    path = dashboards_path("Alice", "personal")
    write_json(
        path,
        {
            "dashboards": [
                {
                    "id": "d1",
                    "owner": "Alice",
                    "blocks": [{"id": "b1", "type": "pool_tasks", "config": {}}],
                }
            ]
        },
    )

    from module_packages.household.manifest import m023_rename_pool_tasks_block_type

    m023_rename_pool_tasks_block_type(brain)
    m023_rename_pool_tasks_block_type(brain)  # run twice — must not double-rename or error

    data = read_json(path, default={})
    assert data["dashboards"][0]["blocks"][0]["type"] == "household_tasks"
