"""Integration tests for notes' conversion into module_packages/ (increment
— Notes, 2026-08-26) — not notes_service's own CRUD/sharing logic (covered
by test_notes_service.py/test_notes_sharing.py, stays core) or the router's
own body logic (covered by module_packages/notes/tests/test_notes_router.py):
the m026 upgrade migration (features.json-existence guard, same idiom as
journal's m015/automations' m019/calendar's m020/household's m022 — notes
was always-on before this system existed), a full install/uninstall/
reinstall round-trip, and the three real, pre-existing enforcement gaps this
conversion closes — none of them invented by the conversion, all three
found during its own upfront research pass:

1. All 7 note AI tools lived in agent_service.py's unfiltered static
   _USER_TOOLS list, so a user with Notes disabled could still use them via
   chat — module-owned tools are the only ones _get_tools() filters by
   disabled_modules.
2. No owned_brain_paths entry meant a disabled user's own Notes/ folder was
   fully readable via the Brain browser and the AI's own file-reading tools
   regardless of module state.
3. The note_embed dashboard block had no module= gate at all (the exact
   pool_tasks-before-Household/Team situation) — shown in the block picker
   regardless of module state."""

from migrations.runner import run_pending
from services import mod_store_service


def test_m026_marks_notes_installed_on_upgrade(brain):
    (brain / "_system" / "features.json").write_text('{"profile": "personal", "roles": {}}')

    run_pending(brain)

    assert mod_store_service.is_installed("notes")


def test_m026_noop_on_fresh_install(brain):
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("notes")


def test_install_uninstall_reinstall_round_trip_preserves_data(brain):
    from services import notes_service

    notes_service.create_note("dana", "Recipe", "eggs", "personal")

    mod_store_service.mark_installed("notes", by="tester")
    assert mod_store_service.is_installed("notes")

    mod_store_service.mark_uninstalled("notes", by="tester")
    assert not mod_store_service.is_installed("notes")
    # data untouched even while "uninstalled"
    assert notes_service.get_note("dana", "Recipe", "personal")["content"] == "eggs"

    mod_store_service.mark_installed("notes", by="tester")
    assert mod_store_service.is_installed("notes")
    assert notes_service.get_note("dana", "Recipe", "personal")["content"] == "eggs"


def test_notes_ai_tools_hidden_when_module_disabled(brain):
    """Gap #1 — before this conversion, the 7 note tools lived in the static
    _USER_TOOLS list, unfiltered by disabled_modules. Now they're
    module-owned, so _get_tools()'s existing owned_by_disabled filter
    applies to them for the first time."""
    from services import agent_service

    mod_store_service.mark_installed("notes", by="tester")

    enabled_user = {"name": "alice", "disabled_modules": [], "role": "member"}
    disabled_user = {"name": "alice", "disabled_modules": ["notes"], "role": "member"}

    enabled_names = {t["name"] for t in agent_service._get_tools(enabled_user)}
    disabled_names = {t["name"] for t in agent_service._get_tools(disabled_user)}

    assert "list_notes" in enabled_names
    assert "create_note" in enabled_names
    assert "list_notes" not in disabled_names
    assert "create_note" not in disabled_names
    # search_brain is NOT a notes tool — stays available regardless.
    assert "search_brain" in disabled_names


def test_notes_brain_folder_hidden_from_browser_when_notes_disabled(brain):
    """Gap #2 — owned_brain_paths=["Notes"] closes a real, previously-open
    gap: a disabled user's own Notes/ folder had zero Brain-browser/AI-tool
    protection before this conversion."""
    from module_registry import brain_paths_for_disabled

    assert "Notes" in brain_paths_for_disabled({"notes"})
    assert "Notes" not in brain_paths_for_disabled(set())


def test_note_embed_block_gated_by_module_state(brain):
    """Gap #3 — note_embed had no module= gate at all before this
    conversion, the same pool_tasks-before-Household/Team situation."""
    from services.dashboard_blocks import registry

    registry._load_all_resolvers()

    cat_disabled = registry.catalog(is_admin=False, disabled_modules={"notes"})
    assert "note_embed" not in {c["type"] for c in cat_disabled}

    cat_enabled = registry.catalog(is_admin=False, disabled_modules=set())
    assert "note_embed" in {c["type"] for c in cat_enabled}
