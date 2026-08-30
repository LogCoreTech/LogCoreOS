"""Integration tests for contacts' conversion into module_packages/
(increment — Contacts, 2026-08-28) — the second of the three largest
remaining modules (Assets, Contacts, Finance). Not contacts_service's own
CRUD/sharing/self-contact/affiliation logic (covered extensively by
tests/test_contacts.py, stays core): the m029 upgrade migration
(features.json-existence guard, same idiom as journal's m015/calendar's
m020/notes' m026/assets' m028 — contacts was always-on before this system
existed), a full install/uninstall/reinstall round-trip, and the real,
pre-existing enforcement gaps this conversion closes — none of them
invented by the conversion, all found during its own upfront research
pass:

1. All 6 contact AI tools lived in agent_service.py's unfiltered static
   _USER_TOOLS list, so a user with Contacts disabled could still use them
   via chat — module-owned tools are the only ones _get_tools() actually
   filters by disabled_modules. Unlike Assets, Contacts owns no admin-only
   tool, so there's no admin_agent_tools test here.
2. linked_deals/contacts_list/linked_assets all had no module= gate at
   all — shown in the block picker and rendered regardless of module
   state. The fourth contact-adjacent block, custom_fields, deliberately
   stays ungated (it reads from either contacts_service OR assets_service
   depending on config, the same "owned by none" shape as nav_button/
   status_button) — this file confirms that block is NOT affected by
   Contacts being disabled, the flip side of the other three's own test.
3. PUT /contacts/fields (admin custom-field-schema authoring) had
   require_admin but no require_module("contacts"), unlike its own GET
   sibling — closed by adding require_module alongside require_admin.
   GET /contacts/available-for-linking is DELIBERATELY left as-is (no
   require_module), matching GET/PATCH /contacts/me's own precedent —
   confirmed here too, as a "stays working" assertion, not a gap."""

from migrations.runner import run_pending
from services import mod_store_service


def test_m029_marks_contacts_installed_on_upgrade(brain):
    (brain / "_system" / "features.json").write_text('{"profile": "personal", "roles": {}}')

    run_pending(brain)

    assert mod_store_service.is_installed("contacts")


def test_m029_noop_on_fresh_install(brain):
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("contacts")


def test_install_uninstall_reinstall_round_trip_preserves_data(brain):
    from services import contacts_service

    contacts_service.create_contact("dana", "personal", {"name": "Erin"}, created_by="dana")

    mod_store_service.mark_installed("contacts", by="tester")
    assert mod_store_service.is_installed("contacts")

    mod_store_service.mark_uninstalled("contacts", by="tester")
    assert not mod_store_service.is_installed("contacts")
    # data untouched even while "uninstalled"
    assert contacts_service.list_contacts("dana", "personal")[0]["name"] == "Erin"

    mod_store_service.mark_installed("contacts", by="tester")
    assert mod_store_service.is_installed("contacts")
    assert contacts_service.list_contacts("dana", "personal")[0]["name"] == "Erin"


def test_contacts_ai_tools_hidden_when_module_disabled(brain):
    """Gap #1 — before this conversion, all 6 contact tools lived unfiltered
    in the static _USER_TOOLS list. Now they're module-owned, so
    _get_tools()'s existing owned_by_disabled filter applies to them for
    the first time."""
    from services import agent_service

    mod_store_service.mark_installed("contacts", by="tester")

    enabled_user = {"name": "alice", "disabled_modules": [], "role": "member"}
    disabled_user = {"name": "alice", "disabled_modules": ["contacts"], "role": "member"}

    enabled_names = {t["name"] for t in agent_service._get_tools(enabled_user)}
    disabled_names = {t["name"] for t in agent_service._get_tools(disabled_user)}

    assert "list_contacts" in enabled_names
    assert "create_deal" in enabled_names
    assert "list_contacts" not in disabled_names
    assert "create_deal" not in disabled_names
    # update_profile/get_profile stay core — unaffected by Contacts' own
    # module state, matching /contacts/me's own deliberate module-gate-free
    # design (see manifest.py's docstring).
    assert "update_profile" in disabled_names


def test_contacts_blocks_gated_by_module_state(brain):
    """Gap #2 — linked_deals/contacts_list/linked_assets all had no module=
    gate at all before this conversion. custom_fields deliberately stays
    ungated, confirmed here as the flip side of the other three."""
    from services.dashboard_blocks import registry

    registry._load_all_resolvers()

    cat_disabled = registry.catalog(is_admin=False, disabled_modules={"contacts"})
    disabled_types = {c["type"] for c in cat_disabled}
    for t in ("linked_deals", "contacts_list", "linked_assets"):
        assert t not in disabled_types
    assert "custom_fields" in disabled_types

    cat_enabled = registry.catalog(is_admin=False, disabled_modules=set())
    enabled_types = {c["type"] for c in cat_enabled}
    for t in ("linked_deals", "contacts_list", "linked_assets", "custom_fields"):
        assert t in enabled_types


def test_fields_admin_endpoint_now_module_gated(brain):
    """Gap #3 — PUT /contacts/fields had require_admin but no
    require_module, unlike its own GET sibling. Direct-call convention
    can't exercise Depends(_require_contacts) itself (same documented,
    pre-existing suite-wide limitation as require_module everywhere else in
    this suite), so this test instead confirms the dependency is now
    actually wired onto the endpoint — the parameter existing at all is the
    fix; whether FastAPI enforces it is proven by every other require_module
    dependency already trusted throughout this suite."""
    import inspect

    from module_packages.contacts.backend.router import set_fields

    params = inspect.signature(set_fields).parameters
    assert "_module" in params


def test_available_for_linking_deliberately_stays_module_gate_free(brain):
    """The flip side of gap #3 — confirms this one is a deliberate match to
    GET/PATCH /contacts/me's precedent, not an oversight left unfixed."""
    import inspect

    from module_packages.contacts.backend.router import list_contacts_available_for_linking

    params = inspect.signature(list_contacts_available_for_linking).parameters
    assert set(params) == {"current_user", "_rl"}
