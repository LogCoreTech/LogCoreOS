"""Integration tests for finance's conversion into module_packages/
(increment — Finance, 2026-08-28) — the last and largest of the three
biggest remaining modules (Assets, Contacts, Finance, deliberately last),
and the only one split across SIX router files rather than one. Not
finance_service.py's own CRUD/access-resolution logic (covered extensively
by tests/test_finance_service.py/test_finance_sharing.py/
test_finance_planning.py/test_finance_invoices.py, all stay core): the
m030 upgrade migration (features.json-existence guard, same idiom as every
prior conversion's own), a full install/uninstall/reinstall round-trip,
and the real, pre-existing enforcement gaps this conversion closes — none
of them invented by the conversion, all found during its own upfront
research pass:

1. All 9 finance AI tools lived in agent_service.py's unfiltered static
   _USER_TOOLS list, so a user with Finance disabled could still use them
   via chat — module-owned tools are the only ones _get_tools() actually
   filters by disabled_modules. No admin-only Finance tool exists, so
   there's no admin_agent_tools test here.
2. finance_activity/finance_book_report both had no module= gate at all —
   shown in the block picker and rendered regardless of module state.
3. 13 admin-lifecycle SimpleFIN endpoints inside finance_banking.py had
   require_admin but no require_module("finance") — an admin whose own
   account has Finance disabled could still manage every user's bank
   connections. Fixed by adding require_module alongside require_admin on
   all 13, the same narrow-inconsistency shape as Contacts' own
   PUT /contacts/fields finding, confirmed here by inspecting one
   representative endpoint's own dependency signature (the direct-call
   convention can't exercise Depends() enforcement itself, the same
   documented, pre-existing suite-wide limitation noted in every prior
   conversion's own router test file)."""

from migrations.runner import run_pending
from services import mod_store_service


def test_m030_marks_finance_installed_on_upgrade(brain):
    (brain / "_system" / "features.json").write_text('{"profile": "personal", "roles": {}}')

    run_pending(brain)

    assert mod_store_service.is_installed("finance")


def test_m030_noop_on_fresh_install(brain):
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("finance")


def test_install_uninstall_reinstall_round_trip_preserves_data(brain):
    from services import finance_service

    finance_service.create_book("dana", "personal", name="Dana's Book", created_by="dana")

    mod_store_service.mark_installed("finance", by="tester")
    assert mod_store_service.is_installed("finance")

    mod_store_service.mark_uninstalled("finance", by="tester")
    assert not mod_store_service.is_installed("finance")
    # data untouched even while "uninstalled"
    assert (
        finance_service.list_visible_books("dana", "member", False, "personal")[0]["name"]
        == "Dana's Book"
    )

    mod_store_service.mark_installed("finance", by="tester")
    assert mod_store_service.is_installed("finance")
    assert (
        finance_service.list_visible_books("dana", "member", False, "personal")[0]["name"]
        == "Dana's Book"
    )


def test_finance_ai_tools_hidden_when_module_disabled(brain):
    """Gap #1 — before this conversion, all 9 finance tools lived unfiltered
    in the static _USER_TOOLS list. Now they're module-owned, so
    _get_tools()'s existing owned_by_disabled filter applies to them for
    the first time."""
    from services import agent_service

    mod_store_service.mark_installed("finance", by="tester")

    enabled_user = {"name": "alice", "disabled_modules": [], "role": "member"}
    disabled_user = {"name": "alice", "disabled_modules": ["finance"], "role": "member"}

    enabled_names = {t["name"] for t in agent_service._get_tools(enabled_user)}
    disabled_names = {t["name"] for t in agent_service._get_tools(disabled_user)}

    assert "list_finance_books" in enabled_names
    assert "create_invoice" in enabled_names
    assert "list_finance_books" not in disabled_names
    assert "create_invoice" not in disabled_names


def test_finance_blocks_gated_by_module_state(brain):
    """Gap #2 — finance_activity/finance_book_report both had no module=
    gate at all before this conversion."""
    from services.dashboard_blocks import registry

    registry._load_all_resolvers()

    cat_disabled = registry.catalog(is_admin=False, disabled_modules={"finance"})
    disabled_types = {c["type"] for c in cat_disabled}
    for t in ("finance_activity", "finance_book_report"):
        assert t not in disabled_types

    cat_enabled = registry.catalog(is_admin=False, disabled_modules=set())
    enabled_types = {c["type"] for c in cat_enabled}
    for t in ("finance_activity", "finance_book_report"):
        assert t in enabled_types


def test_simplefin_admin_endpoints_now_module_gated(brain):
    """Gap #3 — the 13 admin-lifecycle SimpleFIN endpoints had require_admin
    but no require_module. Direct-call convention can't exercise
    Depends(_require_finance) itself (same documented, pre-existing
    suite-wide limitation as require_module everywhere else in this
    suite), so this test instead confirms the dependency is now actually
    wired onto every one of them — the parameter existing at all is the
    fix; whether FastAPI enforces it is proven by every other
    require_module dependency already trusted throughout this suite."""
    import inspect

    from module_packages.finance.backend import router_banking

    admin_endpoints = [
        router_banking.list_connections,
        router_banking.pool_bank_summary,
        router_banking.claim_for_user,
        router_banking.reveal_access_url,
        router_banking.disconnect_user,
        router_banking.sync_now,
        router_banking.pool_status,
        router_banking.pool_bank_accounts,
        router_banking.pool_set_mapping,
        router_banking.pool_claim,
        router_banking.pool_reveal,
        router_banking.pool_disconnect,
        router_banking.pool_sync_now,
    ]
    assert len(admin_endpoints) == 13
    for fn in admin_endpoints:
        params = inspect.signature(fn).parameters
        assert "_module" in params, f"{fn.__name__} is missing the require_module gate"


def test_finance_router_assembles_all_six_sub_routers(brain):
    """The manifest's _get_router() composes 6 separate router files into
    one — confirms the combined router has all 78 original endpoints and
    keeps each sub-router's own original tag (no new umbrella tag added,
    so the OpenAPI grouping stays byte-identical to before this
    conversion)."""
    from module_packages.finance.manifest import MODULE

    router = MODULE.get_router()
    tags = set()
    for route in router.routes:
        tags.update(route.tags)

    assert len(router.routes) == 78
    assert tags == {
        "finance",
        "finance-banking",
        "finance-planning",
        "finance-invoicing",
        "finance-sharing",
        "finance-transfers",
    }
