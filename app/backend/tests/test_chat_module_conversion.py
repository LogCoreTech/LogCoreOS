"""Integration tests for chat's conversion into module_packages/ (increment
— Chat, 2026-08-26) — the second LOCKED (uninstallable=True) module after
Tasks. Mirrors test_tasks_module_conversion.py's own shape exactly: not
agent_service.py's own logic (stays core, already covered elsewhere), the
conversion machinery itself — m025's unconditional migration, a real
discovery-path proof that a broken locked module crashes boot, and that the
Mod Store router genuinely refuses to uninstall it."""

import pytest
from fastapi import HTTPException

from migrations.runner import run_pending
from services import mod_store_service


def test_m025_marks_chat_installed_when_run_fresh(brain):
    """The brain fixture already marks every locked module installed (it
    mirrors what a real boot always does) — reset that here so this test
    isolates the migration function's own logic, not the fixture's."""
    mod_store_service.mark_uninstalled("chat", by="tester")
    assert not mod_store_service.is_installed("chat")

    from module_packages.chat.manifest import m025_mark_chat_installed_unconditionally

    m025_mark_chat_installed_unconditionally(brain)

    assert mod_store_service.is_installed("chat")


def test_m025_has_no_existence_guard_unlike_optional_modules(brain):
    """Unlike journal's m015/automations' m019/calendar's m020/household's
    m022/team's m024 (all guarded on _system/features.json existing), chat
    must install unconditionally even on a brain with no features.json at
    all — it was never optional, same as tasks' own m021."""
    assert not (brain / "_system" / "features.json").exists()
    mod_store_service.mark_uninstalled("chat", by="tester")

    run_pending(brain)

    assert mod_store_service.is_installed("chat")


def test_locked_module_boot_crash_via_real_discovery_path(monkeypatch, brain):
    """test_module_registry.py already proves the generic mechanism with a
    synthetic fake module, and test_tasks_module_conversion.py proved it for
    the first real locked module — this proves it holds for chat too, the
    second real, shipped locked manifest."""
    from fastapi import FastAPI

    import module_registry
    from module_packages.chat import manifest as chat_manifest

    def _broken_router():
        raise RuntimeError("chat router is broken")

    monkeypatch.setattr(chat_manifest.MODULE, "get_router", _broken_router)

    app = FastAPI()
    with pytest.raises(module_registry.LockedModuleRegistrationError):
        module_registry.register_routers(app)


def test_uninstall_chat_rejected_through_the_real_router(brain):
    from routers.mod_store import uninstall
    from services import auth_service

    admin = auth_service.create_user("admin@example.com", "password123", "Admin", role="admin")
    assert mod_store_service.is_installed("chat")

    with pytest.raises(HTTPException) as exc:
        uninstall("chat", admin)

    assert exc.value.status_code == 400
    assert mod_store_service.is_installed("chat")


def test_chats_brain_folder_hidden_from_browser_when_chat_disabled(brain):
    """owned_brain_paths=["Chats"] — the real enforcement gap this
    conversion closes: a disabled user's own chat archives must disappear
    from the generic Brain file browser the same way every other module's
    owned path already does, conditional on THAT user's own disabled state
    (not the unconditional Tasks/Business exception)."""
    from module_registry import brain_paths_for_disabled

    assert "Chats" in brain_paths_for_disabled({"chat"})
    assert "Chats" not in brain_paths_for_disabled(set())
