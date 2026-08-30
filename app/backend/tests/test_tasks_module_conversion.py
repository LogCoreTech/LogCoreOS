"""Integration tests for tasks' conversion into module_packages/ (increment
— Tasks, 2026-08-25) — the first LOCKED (uninstallable=True) module. Not
task_service's own CRUD logic (already covered by test_task_service.py,
unaffected since it stays in core) — the conversion machinery itself: the
m021 upgrade migration (unconditional, no existence-guard, since Tasks was
never optional), the real discovery-path proof that a broken locked module
crashes boot (test_module_registry.py already covers this generically with
a synthetic fake module; this file adds the real one), and that the Mod
Store router genuinely refuses to uninstall it."""

import pytest
from fastapi import HTTPException

from migrations.runner import run_pending
from services import mod_store_service


def test_m021_marks_tasks_installed_when_run_fresh(brain):
    """The brain fixture already marks every locked module installed (it
    mirrors what a real boot always does) — reset that here so this test
    isolates the migration function's own logic, not the fixture's."""
    mod_store_service.mark_uninstalled("tasks", by="tester")
    assert not mod_store_service.is_installed("tasks")

    from module_packages.tasks.manifest import m021_mark_tasks_installed_unconditionally

    m021_mark_tasks_installed_unconditionally(brain)

    assert mod_store_service.is_installed("tasks")


def test_m021_has_no_existence_guard_unlike_optional_modules(brain):
    """Unlike journal's m015/automations' m019/calendar's m020 (all guarded
    on _system/features.json existing, so a genuinely fresh instance starts
    with that module NOT installed), tasks must install unconditionally even
    on a brain with no features.json at all — it was never optional."""
    assert not (brain / "_system" / "features.json").exists()
    mod_store_service.mark_uninstalled("tasks", by="tester")

    run_pending(brain)

    assert mod_store_service.is_installed("tasks")


def test_locked_module_boot_crash_via_real_discovery_path(monkeypatch, brain):
    """test_module_registry.py already proves the generic mechanism with a
    synthetic fake module; this proves it holds for the real, shipped tasks
    manifest — a broken get_router() on an actually-discovered locked module
    really does crash register_routers(), not just a hand-built fixture."""
    from fastapi import FastAPI

    import module_registry
    from module_packages.tasks import manifest as tasks_manifest

    def _broken_router():
        raise RuntimeError("tasks router is broken")

    monkeypatch.setattr(tasks_manifest.MODULE, "get_router", _broken_router)

    app = FastAPI()
    with pytest.raises(module_registry.LockedModuleRegistrationError):
        module_registry.register_routers(app)


def test_uninstall_tasks_rejected_through_the_real_router(brain):
    from routers.mod_store import uninstall
    from services import auth_service

    admin = auth_service.create_user("admin@example.com", "password123", "Admin", role="admin")
    assert mod_store_service.is_installed("tasks")

    with pytest.raises(HTTPException) as exc:
        uninstall("tasks", admin)

    assert exc.value.status_code == 400
    assert mod_store_service.is_installed("tasks")
