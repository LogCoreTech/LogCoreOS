"""Migration correctness for Goals becoming a real module (2026-08-28) —
the fresh-vs-upgrade guard, the actual legacy type=="goal" Task -> Goal
record conversion (across a real user AND the household/team pools),
idempotency, and the metric-provider registry discovering Finance's/
Contacts' own registered providers once those modules are active. Mirrors
the rigor test_full_upgrade_migration_chain.py already established for the
other 13 modules' own upgrade migrations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from migrations.runner import run_pending
from services import mod_store_service


def _seed_pre_existing_instance(brain):
    from services.file_service import write_json

    (brain / "_system").mkdir(parents=True, exist_ok=True)
    write_json(brain / "_system" / "features.json", {"profile": "personal", "roles": {}})


def test_fresh_install_leaves_goals_not_installed(brain):
    assert not (brain / "_system" / "features.json").exists()
    run_pending(brain)
    assert not mod_store_service.is_installed("goals")


def test_upgrade_marks_goals_installed(brain):
    _seed_pre_existing_instance(brain)
    run_pending(brain)
    assert mod_store_service.is_installed("goals")


def test_upgrade_converts_legacy_goal_tasks_to_real_goals(brain):
    from services import auth_service, task_service
    from module_packages.goals.backend import service as goals_service

    auth_service.create_user("alice@example.com", "password123", "Alice")
    _seed_pre_existing_instance(brain)

    # A real pre-existing type=="goal" task, written directly (bypassing the
    # now-removed Pydantic "goal" literal, matching how a REAL pre-migration
    # instance's tasks.json would already have this on disk).
    legacy = task_service.add_task("Alice", {"title": "Old-style goal", "category": "Health"})
    from services.file_service import read_json, tasks_path, write_json

    data = read_json(tasks_path("Alice"))
    for t in data["tasks"]:
        if t["id"] == legacy["id"]:
            t["type"] = "goal"
            t["due_date"] = "2026-12-31"
    write_json(tasks_path("Alice"), data)

    run_pending(brain)

    # Removed from tasks.json
    remaining = task_service.list_tasks("Alice")
    assert not any(t["id"] == legacy["id"] for t in remaining)

    # Present as a real Goal record with the same id
    goal = goals_service.get_goal("Alice", legacy["id"])
    assert goal is not None
    assert goal["title"] == "Old-style goal"
    assert goal["due_date"] == "2026-12-31"


def test_upgrade_converts_pool_goal_tasks_too(brain):
    from services.file_service import tasks_path, write_json
    from module_packages.goals.backend import service as goals_service

    _seed_pre_existing_instance(brain)
    write_json(
        tasks_path("_household"),
        {
            "tasks": [
                {
                    "id": "pool-goal-1",
                    "title": "Family goal",
                    "category": "Home",
                    "type": "goal",
                    "status": "pending",
                    "due_date": None,
                    "notes": None,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        },
    )

    run_pending(brain)

    goal = goals_service.get_goal("_household", "pool-goal-1")
    assert goal is not None
    assert goal["title"] == "Family goal"


def test_migration_is_idempotent(brain):
    from services import auth_service, task_service

    auth_service.create_user("alice@example.com", "password123", "Alice")
    _seed_pre_existing_instance(brain)
    legacy = task_service.add_task("Alice", {"title": "Once", "category": "Work"})
    from services.file_service import read_json, tasks_path, write_json

    data = read_json(tasks_path("Alice"))
    for t in data["tasks"]:
        if t["id"] == legacy["id"]:
            t["type"] = "goal"
    write_json(tasks_path("Alice"), data)

    first = run_pending(brain)
    second = run_pending(brain)
    assert first > 0
    assert second == 0

    from module_packages.goals.backend import service as goals_service

    all_goals = goals_service.list_goals("Alice")
    assert len([g for g in all_goals if g["id"] == legacy["id"]]) == 1


def test_no_migration_name_collisions(brain):
    from module_registry import discover_manifests

    manifests, errors = discover_manifests()
    collisions = {mid: msg for mid, msg in errors.items() if "collision" in msg}
    assert not collisions
    assert "goals" in manifests


def test_metric_provider_registry_discovers_finance_and_contacts(brain):
    from module_registry import metric_providers

    mod_store_service.mark_installed("finance", by="test")
    mod_store_service.mark_installed("contacts", by="test")

    providers = metric_providers()
    assert "finance:budget_pct" in providers
    assert "contacts:number_field" in providers


def test_metric_provider_absent_when_owning_module_not_installed(brain):
    from module_registry import metric_providers

    providers = metric_providers()
    assert "finance:budget_pct" not in providers
    assert "contacts:number_field" not in providers
