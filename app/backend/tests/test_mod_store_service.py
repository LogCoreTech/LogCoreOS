"""Tests for mod_store_service.py — installed-state tracking, history, and
the catalog merge."""

import pytest

from services import mod_store_service


@pytest.fixture(autouse=True)
def _reset_catalog_cache():
    """The static catalog file content is cached at module scope — reset it
    around each test so one test's monkeypatched catalog never leaks into
    another's."""
    mod_store_service._cache = None
    yield
    mod_store_service._cache = None


def test_catalog_has_field_ops_entry_coming_soon():
    catalog = mod_store_service.get_catalog()
    entry = next((e for e in catalog if e["id"] == "field_ops"), None)
    assert entry is not None
    assert entry["status"] == "coming_soon"
    assert entry["installed"] is False
    assert entry["uninstallable"] is False


def test_install_uninstall_round_trip(brain):
    assert not mod_store_service.is_installed("field_ops")
    mod_store_service.mark_installed("field_ops", by="alice")
    assert mod_store_service.is_installed("field_ops")
    assert "field_ops" in mod_store_service.get_installed_ids()

    mod_store_service.mark_uninstalled("field_ops", by="alice")
    assert not mod_store_service.is_installed("field_ops")


def test_uninstall_never_touches_data(brain):
    """The whole point of 'hide only, never delete' — uninstall only ever
    touches installed_modules.json, never any Brain data file."""
    data_file = brain / "USERS" / "alice" / "Journal" / "2026-01-01.md"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("a real journal entry")

    mod_store_service.mark_installed("field_ops", by="alice")
    mod_store_service.mark_uninstalled("field_ops", by="alice")

    assert data_file.exists()
    assert data_file.read_text() == "a real journal entry"


def test_history_records_install_and_uninstall(brain):
    mod_store_service.mark_installed("field_ops", by="alice")
    mod_store_service.mark_uninstalled("field_ops", by="alice")

    from services.file_service import read_json

    history = read_json(mod_store_service._history_path(), default={"events": []})
    # Filtered to field_ops — the brain fixture itself now writes a real
    # "tasks: install" event too (it marks every locked module installed,
    # matching what every real boot always does since Tasks converted
    # 2026-08-25), legitimate background noise this test shouldn't couple to.
    events = [e for e in history["events"] if e["module_id"] == "field_ops"]
    assert len(events) == 2
    assert events[0]["action"] == "install"
    assert events[0]["by"] == "alice"
    assert events[1]["action"] == "uninstall"


def test_history_survives_reinstall_after_uninstall(brain):
    """installed_modules.json loses install history on uninstall (the key is
    removed entirely) — the separate history file is what preserves it."""
    mod_store_service.mark_installed("field_ops", by="alice")
    mod_store_service.mark_uninstalled("field_ops", by="alice")
    mod_store_service.mark_installed("field_ops", by="bob")

    from services.file_service import read_json

    history = read_json(mod_store_service._history_path(), default={"events": []})
    # Filtered to field_ops — see comment above.
    actions = [(e["action"], e["by"]) for e in history["events"] if e["module_id"] == "field_ops"]
    assert actions == [("install", "alice"), ("uninstall", "alice"), ("install", "bob")]


def test_get_catalog_reflects_error_status(fake_module, brain, monkeypatch):
    import json

    monkeypatch.setattr(
        mod_store_service,
        "_load_catalog_file",
        lambda: {
            "modules": [
                {
                    "id": "t_broken_catalog",
                    "name": "Broken",
                    "description": "d",
                    "icon": "x",
                    "category": "test",
                    "status": "coming_soon",
                }
            ]
        },
    )
    fake_module("t_broken_catalog", "raise ImportError('boom')\n")

    catalog = mod_store_service.get_catalog()
    entry = next(e for e in catalog if e["id"] == "t_broken_catalog")
    assert entry["status"] == "error"
    assert entry["error"] is not None


def test_get_catalog_flips_coming_soon_to_available_once_code_present(
    fake_module, brain, monkeypatch
):
    monkeypatch.setattr(
        mod_store_service,
        "_load_catalog_file",
        lambda: {
            "modules": [
                {
                    "id": "t_now_available",
                    "name": "Now Available",
                    "description": "d",
                    "icon": "x",
                    "category": "test",
                    "status": "coming_soon",
                }
            ]
        },
    )
    src = """
from module_registry import ModuleManifest

def _get_router():
    from module_packages.t_now_available.backend.router import router
    return router

MODULE = ModuleManifest(
    id="t_now_available",
    display_name="Test",
    description="Test",
    icon="x",
    version="1.0.0",
    router_prefix="/api/v1/t_now_available",
    router_tags=["t_now_available"],
    get_router=_get_router,
)
"""
    fake_module("t_now_available", src)

    catalog = mod_store_service.get_catalog()
    entry = next(e for e in catalog if e["id"] == "t_now_available")
    assert entry["status"] == "available"
    assert entry["version"] == "1.0.0"
