"""Tests for the module-system integration in help_service.py: get_content()
merging a discovered module's help_section, and capabilities_index()
describing every module (not just enabled ones) with its real state."""

from services import help_service, mod_store_service

_MANIFEST_WITH_HELP_SRC = """
from module_registry import ModuleManifest

def _get_router():
    from module_packages.t_help_mod.backend.router import router
    return router

MODULE = ModuleManifest(
    id="t_help_mod",
    display_name="Test Help Module",
    description="Test",
    icon="x",
    version="0.0.1",
    router_prefix="/api/v1/t_help_mod",
    router_tags=["t_help_mod"],
    get_router=_get_router,
    help_section={
        "id": "t_help_mod",
        "icon": "x",
        "title": "Test Help Module",
        "blurb": "Does test things. More detail.",
        "modules": ["t_help_mod"],
    },
)
"""


def test_get_content_merges_module_help_section(fake_module):
    fake_module("t_help_mod", _MANIFEST_WITH_HELP_SRC)
    content = help_service.get_content()
    ids = {s["id"] for s in content["sections"]}
    assert "t_help_mod" in ids


def test_capabilities_index_marks_not_installed_module(fake_module, brain):
    fake_module("t_help_mod", _MANIFEST_WITH_HELP_SRC)
    # discovered but never installed
    index = help_service.capabilities_index(enabled_modules=set())
    assert "Test Help Module" in index
    assert "NOT INSTALLED" in index


def test_capabilities_index_marks_disabled_but_installed_module(fake_module, brain):
    fake_module("t_help_mod", _MANIFEST_WITH_HELP_SRC)
    mod_store_service.mark_installed("t_help_mod", by="tester")
    # installed instance-wide, but not in this user's enabled set (role/override disabled)
    index = help_service.capabilities_index(enabled_modules=set())
    module_line = next(line for line in index.splitlines() if "Test Help Module" in line)
    assert "turned off for this user" in module_line
    assert "NOT INSTALLED" not in module_line


def test_capabilities_index_shows_enabled_module_normally(fake_module, brain):
    fake_module("t_help_mod", _MANIFEST_WITH_HELP_SRC)
    mod_store_service.mark_installed("t_help_mod", by="tester")
    index = help_service.capabilities_index(enabled_modules={"t_help_mod"})
    module_line = next(line for line in index.splitlines() if "Test Help Module" in line)
    assert "/help#t_help_mod" in module_line
    assert "NOT INSTALLED" not in module_line
    assert "turned off" not in module_line
