"""Integration tests for dashboard's conversion into module_packages/
(increment — Dashboards, 2026-08-27) — the third LOCKED (uninstallable=True)
module after Tasks and Chat. Mirrors test_chat_module_conversion.py's own
shape exactly: not dashboards_service.py's own logic (stays core, already
covered by test_dashboards_service.py), the conversion machinery itself —
m027's unconditional migration, a real discovery-path proof that a broken
locked module crashes boot, that the Mod Store router genuinely refuses to
uninstall it, and the two real, pre-existing enforcement gaps this
conversion closes (AI tool gating, Brain-folder gating). No dashboard-block
gating test here — Dashboards owns zero block types, unlike every prior
locked/optional module with its own dashboard_block.py."""

import pytest
from fastapi import HTTPException

from migrations.runner import run_pending
from services import mod_store_service


def test_m027_marks_dashboard_installed_when_run_fresh(brain):
    """The brain fixture already marks every locked module installed (it
    mirrors what a real boot always does) — reset that here so this test
    isolates the migration function's own logic, not the fixture's."""
    mod_store_service.mark_uninstalled("dashboard", by="tester")
    assert not mod_store_service.is_installed("dashboard")

    from module_packages.dashboard.manifest import m027_mark_dashboard_installed_unconditionally

    m027_mark_dashboard_installed_unconditionally(brain)

    assert mod_store_service.is_installed("dashboard")


def test_m027_has_no_existence_guard_unlike_optional_modules(brain):
    """Unlike journal's m015/automations' m019/calendar's m020/household's
    m022/team's m024/notes' m026 (all guarded on _system/features.json
    existing), dashboard must install unconditionally even on a brain with
    no features.json at all — it was never optional, same as tasks' own
    m021 and chat's own m025."""
    assert not (brain / "_system" / "features.json").exists()
    mod_store_service.mark_uninstalled("dashboard", by="tester")

    run_pending(brain)

    assert mod_store_service.is_installed("dashboard")


def test_locked_module_boot_crash_via_real_discovery_path(monkeypatch, brain):
    """test_module_registry.py already proves the generic mechanism with a
    synthetic fake module, and test_tasks_module_conversion.py/
    test_chat_module_conversion.py proved it for the first two real locked
    modules — this proves it holds for dashboard too, the third real,
    shipped locked manifest."""
    from fastapi import FastAPI

    import module_registry
    from module_packages.dashboard import manifest as dashboard_manifest

    def _broken_router():
        raise RuntimeError("dashboard router is broken")

    monkeypatch.setattr(dashboard_manifest.MODULE, "get_router", _broken_router)

    app = FastAPI()
    with pytest.raises(module_registry.LockedModuleRegistrationError):
        module_registry.register_routers(app)


def test_uninstall_dashboard_rejected_through_the_real_router(brain):
    from routers.mod_store import uninstall
    from services import auth_service

    admin = auth_service.create_user("admin@example.com", "password123", "Admin", role="admin")
    assert mod_store_service.is_installed("dashboard")

    with pytest.raises(HTTPException) as exc:
        uninstall("dashboard", admin)

    assert exc.value.status_code == 400
    assert mod_store_service.is_installed("dashboard")


def test_dashboards_ai_tools_hidden_when_module_disabled(brain):
    """Gap #1 — before this conversion, the 10 dashboard tools lived in the
    static _USER_TOOLS list, unfiltered by disabled_modules. Now they're
    module-owned, so _get_tools()'s existing owned_by_disabled filter
    applies to them for the first time."""
    from services import agent_service

    enabled_user = {"name": "alice", "disabled_modules": [], "role": "member"}
    disabled_user = {"name": "alice", "disabled_modules": ["dashboard"], "role": "member"}

    enabled_names = {t["name"] for t in agent_service._get_tools(enabled_user)}
    disabled_names = {t["name"] for t in agent_service._get_tools(disabled_user)}

    assert "list_dashboards" in enabled_names
    assert "create_dashboard" in enabled_names
    assert "list_dashboards" not in disabled_names
    assert "create_dashboard" not in disabled_names


def test_dashboards_brain_folder_always_skipped_regardless_of_module_state(brain):
    """Gap #2 — owned_brain_paths=["Dashboards"] is declared for honesty
    (matching Tasks' own precedent), but Dashboards data is JSON, not
    markdown, so it's ALSO unconditionally skipped via the same structural
    exception Tasks/Business get — confirmed both ways here."""
    from module_registry import brain_paths_for_disabled
    from services.agent_service import _brain_skip

    assert "Dashboards" in brain_paths_for_disabled({"dashboard"})
    # Unconditional: skipped even when NOT disabled, unlike a real markdown
    # module's owned path (e.g. Notes, Chats) which only hides when disabled.
    assert "Dashboards" in _brain_skip({"name": "alice", "disabled_modules": []})
