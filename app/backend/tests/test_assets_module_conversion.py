"""Integration tests for assets' conversion into module_packages/ (increment
— Assets, 2026-08-27) — the first of the three largest remaining modules
(Assets, Contacts, Finance). Not assets_service's own CRUD/sharing/caps
logic (covered by tests/test_assets_service.py/test_assets_templates.py,
stays core): the m028 upgrade migration (features.json-existence guard,
same idiom as journal's m015/calendar's m020/notes' m026 — assets was
always-on before this system existed), a full install/uninstall/reinstall
round-trip, and the real, pre-existing enforcement gaps this conversion
closes — none of them invented by the conversion, all found during its own
upfront research pass:

1. All 10 asset AI tools lived in agent_service.py's unfiltered static
   tool lists (_USER_TOOLS/_ADMIN_TOOLS), so a user with Assets disabled
   could still use them via chat — module-owned tools are the only ones
   _get_tools() actually filters by disabled_modules.
2. documents/linked_tasks/linked_contact/my_assets_summary/collection all
   had no module= gate at all — shown in the block picker and rendered
   regardless of module state.
3. The instance-wide n8n automation token's only admin-facing management
   endpoints lived inside this router, gated by nothing but require_admin
   — meaning uninstalling Assets would have silently taken away the
   admin's only way to view/rotate a token Contacts' own automation API
   still depends on. Moved to routers/auth.py's admin section (permanent
   core) as part of this conversion."""

from migrations.runner import run_pending
from services import mod_store_service


def test_m028_marks_assets_installed_on_upgrade(brain):
    (brain / "_system" / "features.json").write_text('{"profile": "personal", "roles": {}}')

    run_pending(brain)

    assert mod_store_service.is_installed("assets")


def test_m028_noop_on_fresh_install(brain):
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("assets")


def test_install_uninstall_reinstall_round_trip_preserves_data(brain):
    from services import assets_service

    assets_service.create_asset("dana", {"name": "Lot 12"}, workspace="personal", created_by="dana")

    mod_store_service.mark_installed("assets", by="tester")
    assert mod_store_service.is_installed("assets")

    mod_store_service.mark_uninstalled("assets", by="tester")
    assert not mod_store_service.is_installed("assets")
    # data untouched even while "uninstalled"
    assert assets_service.list_assets("dana", "personal")[0]["name"] == "Lot 12"

    mod_store_service.mark_installed("assets", by="tester")
    assert mod_store_service.is_installed("assets")
    assert assets_service.list_assets("dana", "personal")[0]["name"] == "Lot 12"


def test_assets_ai_tools_hidden_when_module_disabled(brain):
    """Gap #1 — before this conversion, all 10 asset tools lived unfiltered
    in the static _USER_TOOLS/_ADMIN_TOOLS lists. Now they're module-owned,
    so _get_tools()'s existing owned_by_disabled filter applies to them for
    the first time."""
    from services import agent_service

    mod_store_service.mark_installed("assets", by="tester")

    enabled_admin = {"name": "alice", "disabled_modules": [], "role": "admin"}
    disabled_admin = {"name": "alice", "disabled_modules": ["assets"], "role": "admin"}

    enabled_names = {t["name"] for t in agent_service._get_tools(enabled_admin)}
    disabled_names = {t["name"] for t in agent_service._get_tools(disabled_admin)}

    assert "list_assets" in enabled_names
    assert "delete_asset" in enabled_names  # admin tool, schema-visible to an admin
    assert "list_assets" not in disabled_names
    assert "delete_asset" not in disabled_names


def test_assets_admin_tools_hidden_from_non_admin_regardless_of_module_state(brain):
    """admin_agent_tools controls schema visibility the same way it already
    does for Household's own admin-only tools — a member never sees
    delete_asset/create_asset_template/update_asset_template in their own
    tool list, even with the module fully enabled."""
    from services import agent_service

    mod_store_service.mark_installed("assets", by="tester")

    member = {"name": "bob", "disabled_modules": [], "role": "member"}
    names = {t["name"] for t in agent_service._get_tools(member)}

    assert "list_assets" in names
    assert "delete_asset" not in names
    assert "create_asset_template" not in names
    assert "update_asset_template" not in names


def test_asset_blocks_gated_by_module_state(brain):
    """Gap #2 — documents/linked_tasks/linked_contact/my_assets_summary/
    collection all had no module= gate at all before this conversion."""
    from services.dashboard_blocks import registry

    registry._load_all_resolvers()

    cat_disabled = registry.catalog(is_admin=False, disabled_modules={"assets"})
    disabled_types = {c["type"] for c in cat_disabled}
    for t in ("documents", "linked_tasks", "linked_contact", "my_assets_summary", "collection"):
        assert t not in disabled_types

    cat_enabled = registry.catalog(is_admin=False, disabled_modules=set())
    enabled_types = {c["type"] for c in cat_enabled}
    for t in ("documents", "linked_tasks", "linked_contact", "my_assets_summary", "collection"):
        assert t in enabled_types


def test_automation_token_admin_endpoints_moved_to_auth_router(brain):
    """Gap #3 — the token itself (automations_config.py) stays core and
    shared by both Assets' and Contacts' own automation APIs, but its only
    admin-facing view/rotate endpoints used to live inside this router,
    gated by nothing but require_admin. Confirmed they now live in
    routers/auth.py instead, surviving Assets being uninstalled."""
    from routers.auth import get_automation_token, rotate_automation_token

    admin = {"name": "alice", "role": "admin"}
    result = get_automation_token(admin)
    assert "token" in result

    # And confirmed NOT still present on the assets router itself.
    import module_packages.assets.backend.router as assets_router

    assert not hasattr(assets_router, "get_automation_token")
    assert not hasattr(assets_router, "rotate_automation_token")
