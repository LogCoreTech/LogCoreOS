"""Tests for assets/backend/trash_handlers.py — the per-module side of the
trash registry contract (see services/trash_service.py's module docstring
and module_registry.py's trash_dispatch()/owned_trash_types)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.assets.backend import trash_handlers
from module_packages.assets.manifest import MODULE
from services import auth_service
from services.assets_service import create_asset, delete_asset, get_asset, list_assets
from services.file_service import assets_files_path

USER = "TestUser"


@pytest.fixture()
def user_brain(brain):
    from services import mod_store_service

    mod_store_service.mark_installed("assets", by="test-fixture")
    user_dir = brain / "USERS" / USER / "Assets"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def test_record_types_match_manifest():
    assert trash_handlers.RECORD_TYPES == MODULE.owned_trash_types


def test_describe_uses_name():
    title, subtitle = trash_handlers.describe("asset", {"name": "MacBook Pro"})
    assert title == "MacBook Pro"
    assert subtitle == "Assets"


def test_restore_reinserts_asset(user_brain):
    asset = create_asset(USER, {"name": "Laptop"})
    entry = {"payload": asset, "file_ref": None}

    delete_asset(USER, asset["id"], deleted_by=USER)
    assert get_asset(USER, asset["id"]) is None

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["id"] == asset["id"]
    assert get_asset(USER, asset["id"]) is not None


def test_restore_conflict_raises_when_id_already_present(user_brain):
    asset = create_asset(USER, {"name": "Laptop"})
    entry = {"payload": asset, "file_ref": None}

    with pytest.raises(ValueError):
        trash_handlers.restore(USER, "personal", entry)


def test_restore_clears_dangling_parent_id_with_warning(user_brain):
    parent = create_asset(USER, {"name": "Parent"})
    child = create_asset(USER, {"name": "Child", "parent_id": parent["id"]})

    # Delete the child first (has no children of its own), then remove the
    # parent directly from storage to simulate it having been purged, so the
    # child's trash entry now points at a parent_id that no longer exists.
    delete_asset(USER, child["id"], deleted_by=USER)
    from services.assets_service import _load, _save

    store = _load(USER, "personal")
    store["assets"] = [a for a in store["assets"] if a["id"] != parent["id"]]
    _save(USER, "personal", store)

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    entry = next(e for e in entries if e["original_id"] == child["id"])

    restored = trash_handlers.restore(USER, "personal", entry)
    assert restored["parent_id"] is None
    assert "_warning" in restored
    assert get_asset(USER, child["id"])["parent_id"] is None


def test_restore_moves_attachment_files_back(user_brain):
    asset = create_asset(USER, {"name": "With files"})
    files_dir = assets_files_path(USER, "personal") / asset["id"]
    files_dir.mkdir(parents=True)
    (files_dir / "photo.jpg").write_bytes(b"fake image bytes")

    delete_asset(USER, asset["id"], deleted_by=USER)
    assert not files_dir.exists()

    from services import trash_service

    entries = trash_service.list_trash_for_user({"name": USER, "disabled_modules": []}, "personal")
    entry = next(e for e in entries if e["original_id"] == asset["id"])
    assert entry["file_ref"] is not None

    trash_handlers.restore(USER, "personal", entry)
    assert files_dir.exists()
    assert (files_dir / "photo.jpg").read_bytes() == b"fake image bytes"


def test_access_check_always_true():
    assert trash_handlers.access_check({"name": USER}, "personal", {}) is True
