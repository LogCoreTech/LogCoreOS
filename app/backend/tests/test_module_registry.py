"""Tests for module_registry.py — the discovery/registration mechanism the
whole Mod Store system rides on. Uses the `fake_module` fixture (conftest.py)
to write real module_packages/<id>/ packages to disk for the duration of
each test, since this is a real importlib-based discovery path, not
something worth mocking around.
"""

import pytest
from fastapi import FastAPI

import module_registry


def _good_manifest_src(module_id: str, uninstallable: bool = False) -> str:
    return f"""
from module_registry import ModuleManifest

def _get_router():
    from module_packages.{module_id}.backend.router import router
    return router

MODULE = ModuleManifest(
    id="{module_id}",
    display_name="Test Module",
    description="A fake module for testing.",
    icon="\U0001f9ea",
    version="0.0.1",
    router_prefix="/api/v1/{module_id}",
    router_tags=["{module_id}"],
    get_router=_get_router,
    uninstallable={uninstallable!r},
)
"""


def test_discover_manifests_finds_valid_module(fake_module):
    fake_module("t_valid", _good_manifest_src("t_valid"))
    manifests, errors = module_registry.discover_manifests()
    assert "t_valid" in manifests
    assert manifests["t_valid"].id == "t_valid"
    assert "t_valid" not in errors


def test_discover_manifests_skips_malformed_module(fake_module):
    fake_module("t_broken", "raise ImportError('boom')\n")
    fake_module("t_ok", _good_manifest_src("t_ok"))

    manifests, errors = module_registry.discover_manifests()

    assert "t_broken" not in manifests
    assert "t_broken" in errors
    assert "t_ok" in manifests  # one broken module never blocks discovery of others


def test_discover_manifests_rejects_id_mismatch(fake_module):
    # manifest.id doesn't match its own directory name
    fake_module("t_mismatch", _good_manifest_src("some_other_id"))
    manifests, errors = module_registry.discover_manifests()
    assert "t_mismatch" not in manifests
    assert "t_mismatch" in errors


def test_migration_collision_excludes_module(fake_module):
    from migrations.runner import MIGRATIONS

    core_name = MIGRATIONS[0][0]  # a real, already-used core migration name
    src = f"""
from module_registry import ModuleManifest

def _noop(brain):
    pass

def _get_router():
    from module_packages.t_collide.backend.router import router
    return router

MODULE = ModuleManifest(
    id="t_collide",
    display_name="Test",
    description="Test",
    icon="x",
    version="0.0.1",
    router_prefix="/api/v1/t_collide",
    router_tags=["t_collide"],
    get_router=_get_router,
    migrations=[({core_name!r}, _noop)],
)
"""
    fake_module("t_collide", src)
    manifests, errors = module_registry.discover_manifests()
    assert "t_collide" not in manifests
    assert "t_collide" in errors
    assert "collision" in errors["t_collide"]


def test_active_manifests_filters_by_installed(fake_module, brain):
    from services import mod_store_service

    fake_module("t_optional", _good_manifest_src("t_optional"))
    assert "t_optional" not in module_registry.active_manifests()

    mod_store_service.mark_installed("t_optional", by="tester")
    assert "t_optional" in module_registry.active_manifests()


def test_register_routers_isolates_optional_failure(fake_module, brain):
    from services import mod_store_service

    fake_module("t_broken_router", "raise RuntimeError('router boom')\n")
    fake_module("t_good_router", _good_manifest_src("t_good_router"))
    mod_store_service.mark_installed("t_broken_router", by="tester")
    mod_store_service.mark_installed("t_good_router", by="tester")

    app = FastAPI()
    registered = module_registry.register_routers(app)

    assert "t_good_router" in registered
    assert "t_broken_router" not in registered
    paths = {r.path for r in app.router.routes}
    assert "/api/v1/t_good_router/ping" in paths


def test_register_routers_locked_module_failure_crashes_boot(fake_module, brain):
    from services import mod_store_service

    # A manifest whose get_router() itself raises — locked modules must fail
    # loud, not be silently skipped like an optional module would be.
    src = f"""
from module_registry import ModuleManifest

def _get_router():
    raise RuntimeError("this locked module's router is broken")

MODULE = ModuleManifest(
    id="t_locked_broken",
    display_name="Test",
    description="Test",
    icon="x",
    version="0.0.1",
    router_prefix="/api/v1/t_locked_broken",
    router_tags=["t_locked_broken"],
    get_router=_get_router,
    uninstallable=True,
)
"""
    fake_module("t_locked_broken", src)
    mod_store_service.mark_installed("t_locked_broken", by="tester")

    app = FastAPI()
    with pytest.raises(module_registry.LockedModuleRegistrationError):
        module_registry.register_routers(app)


def test_brain_paths_for_disabled_only_includes_disabled_modules(fake_module):
    src = f"""
from module_registry import ModuleManifest

def _get_router():
    from module_packages.t_brainpaths.backend.router import router
    return router

MODULE = ModuleManifest(
    id="t_brainpaths",
    display_name="Test",
    description="Test",
    icon="x",
    version="0.0.1",
    router_prefix="/api/v1/t_brainpaths",
    router_tags=["t_brainpaths"],
    get_router=_get_router,
    owned_brain_paths=["TestFolder"],
)
"""
    fake_module("t_brainpaths", src)

    assert module_registry.brain_paths_for_disabled(set()) == set()
    assert module_registry.brain_paths_for_disabled({"t_brainpaths"}) == {"TestFolder"}
