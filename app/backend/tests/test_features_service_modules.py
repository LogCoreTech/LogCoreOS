"""Tests for the module-system integration in features_service.py:
all_module_ids() and get_effective_disabled()'s not-installed union."""

from services import features_service, mod_store_service

_GOOD_MANIFEST = """
from module_registry import ModuleManifest

def _get_router():
    from module_packages.{id}.backend.router import router
    return router

MODULE = ModuleManifest(
    id="{id}",
    display_name="Test",
    description="Test",
    icon="x",
    version="0.0.1",
    router_prefix="/api/v1/{id}",
    router_tags=["{id}"],
    get_router=_get_router,
)
"""


def test_all_module_ids_matches_core_list_with_no_modules_installed():
    assert features_service.all_module_ids() == features_service._CORE_MODULE_IDS


def test_all_module_ids_includes_active_module(fake_module, brain):
    fake_module("t_feat_active", _GOOD_MANIFEST.format(id="t_feat_active"))
    mod_store_service.mark_installed("t_feat_active", by="tester")

    ids = features_service.all_module_ids()
    assert "t_feat_active" in ids
    assert set(features_service._CORE_MODULE_IDS).issubset(set(ids))


def test_all_module_ids_excludes_discovered_but_not_installed(fake_module, brain):
    fake_module("t_feat_inactive", _GOOD_MANIFEST.format(id="t_feat_inactive"))
    # never marked installed
    assert "t_feat_inactive" not in features_service.all_module_ids()


def test_get_effective_disabled_includes_not_installed_module(fake_module, brain):
    fake_module("t_feat_disabled", _GOOD_MANIFEST.format(id="t_feat_disabled"))
    # discovered but never installed
    disabled = features_service.get_effective_disabled("member", [], "personal")
    assert "t_feat_disabled" in disabled


def test_get_effective_disabled_excludes_installed_module(fake_module, brain):
    fake_module("t_feat_installed", _GOOD_MANIFEST.format(id="t_feat_installed"))
    mod_store_service.mark_installed("t_feat_installed", by="tester")
    disabled = features_service.get_effective_disabled("member", [], "personal")
    assert "t_feat_installed" not in disabled


def test_get_effective_disabled_still_unions_role_and_user_overrides(brain):
    # Unrelated to modules — confirms the pre-existing behavior wasn't broken
    # by threading the not_installed union through.
    disabled = features_service.get_effective_disabled("member", ["notes"], "personal")
    assert "notes" in disabled
