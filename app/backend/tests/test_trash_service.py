"""Tests for the core soft-delete/restore/purge primitive. Exercises it
through task_service.delete_task (the first wired-in module) rather than
calling trash_service.soft_delete() directly with a synthetic module, since
restore()/access_check() dispatch through module_registry.trash_dispatch(),
which only knows about REAL, active modules — tasks is a locked module, so
the `brain` fixture always has it installed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import auth_service, task_service, trash_service
from services.file_service import read_json, tasks_path

USER = "TestUser"


@pytest.fixture()
def user_brain(brain):
    user_dir = brain / "USERS" / USER / "Tasks"
    user_dir.mkdir(parents=True, exist_ok=True)
    auth_service.create_user("user@example.com", "password123", USER)
    return brain


def _make_task(title="Test Task", category="Work"):
    return {
        "title": title,
        "category": category,
        "priority": "High",
        "type": "todo",
        "recurrence": None,
        "due_date": None,
        "due_time": None,
        "notes": None,
    }


def _user_dict(name=USER, disabled=None, role="admin"):
    return {"name": name, "disabled_modules": disabled or [], "role": role}


def test_soft_delete_writes_index_before_any_move(user_brain):
    """soft_delete() itself never moves a file for a pure-JSON record like a
    task, but the index write must still land regardless — this is the
    baseline every file-moving module (notes, assets, finance) builds on."""
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)

    data = read_json(trash_service._trash_json_path(USER, "personal"))
    assert len(data["entries"]) == 1
    entry = data["entries"][0]
    assert entry["module"] == "tasks"
    assert entry["record_type"] == "task"
    assert entry["original_id"] == task["id"]
    assert entry["deleted_by"] == USER
    assert entry["payload"]["title"] == "Test Task"
    assert entry["file_ref"] is None


def test_list_trash_for_user_excludes_other_users(user_brain):
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)

    mine = trash_service.list_trash_for_user(_user_dict(USER), "personal")
    assert any(e["original_id"] == task["id"] for e in mine)

    other = trash_service.list_trash_for_user(_user_dict("SomeoneElse"), "personal")
    assert all(e["original_id"] != task["id"] for e in other)


def test_restore_round_trip(user_brain):
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)
    assert task_service.get_task(USER, task["id"]) is None

    entries = trash_service.list_trash_for_user(_user_dict(USER), "personal")
    entry_id = next(e["id"] for e in entries if e["original_id"] == task["id"])

    restored = trash_service.restore(
        store_user=USER, workspace="personal", entry_id=entry_id, actor=USER
    )
    assert restored["id"] == task["id"]
    assert task_service.get_task(USER, task["id"]) is not None

    # Entry is gone from Trash after a successful restore
    entries_after = trash_service.list_trash_for_user(_user_dict(USER), "personal")
    assert all(e["id"] != entry_id for e in entries_after)


def test_restore_conflict_raises_value_error(user_brain):
    """Restoring into a slot a same-ID task already occupies (e.g. re-added
    by hand before the restore) is a real conflict, not a silent overwrite."""
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)
    entries = trash_service.list_trash_for_user(_user_dict(USER), "personal")
    entry_id = next(e["id"] for e in entries if e["original_id"] == task["id"])

    # Re-insert a task with the same id directly, simulating the conflict
    def _readd(data):
        data.setdefault("tasks", []).append(task)
        return data

    from services.file_service import update_json

    update_json(tasks_path(USER), _readd, default={"tasks": []})

    with pytest.raises(ValueError):
        trash_service.restore(store_user=USER, workspace="personal", entry_id=entry_id, actor=USER)


def test_purge_one_removes_entry_immediately(user_brain):
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)
    entries = trash_service.list_trash_for_user(_user_dict(USER), "personal")
    entry_id = next(e["id"] for e in entries if e["original_id"] == task["id"])

    assert trash_service.purge_one(store_user=USER, workspace="personal", entry_id=entry_id) is True
    assert (
        trash_service.purge_one(store_user=USER, workspace="personal", entry_id=entry_id) is False
    )

    entries_after = trash_service.list_trash_for_user(_user_dict(USER), "personal")
    assert all(e["id"] != entry_id for e in entries_after)


def test_purge_expired_only_removes_past_entries(user_brain, monkeypatch):
    task_a = task_service.add_task(USER, _make_task("Old task"))
    task_b = task_service.add_task(USER, _make_task("Fresh task"))
    task_service.delete_task(USER, task_a["id"], deleted_by=USER)
    task_service.delete_task(USER, task_b["id"], deleted_by=USER)

    # Backdate task_a's entry so it's already expired
    def _backdate(data):
        for e in data["entries"]:
            if e["original_id"] == task_a["id"]:
                e["expires_at"] = "2000-01-01T00:00:00+00:00"
        return data

    from services.file_service import update_json

    update_json(
        trash_service._trash_json_path(USER, "personal"), _backdate, default={"entries": []}
    )

    results = trash_service.purge_expired()
    assert results.get(f"{USER}/personal") == 1

    data = read_json(trash_service._trash_json_path(USER, "personal"))
    remaining_ids = {e["original_id"] for e in data["entries"]}
    assert task_a["id"] not in remaining_ids
    assert task_b["id"] in remaining_ids


def test_restore_module_unavailable_raises_real_error(user_brain, monkeypatch):
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)
    entries = trash_service.list_trash_for_user(_user_dict(USER), "personal")
    entry_id = next(e["id"] for e in entries if e["original_id"] == task["id"])

    # Simulate the module having become unavailable by clearing the dispatch
    # table's knowledge of it entirely.
    monkeypatch.setattr("module_registry.trash_dispatch", lambda: {})

    with pytest.raises(trash_service.TrashModuleUnavailable):
        trash_service.restore(store_user=USER, workspace="personal", entry_id=entry_id, actor=USER)


def test_allowed_stores_for_excludes_disabled_pool(user_brain):
    stores = trash_service.allowed_stores_for(_user_dict(USER, role="admin"), "personal")
    assert (USER, "personal") in stores
    assert ("_household", "personal") in stores

    stores_disabled = trash_service.allowed_stores_for(
        _user_dict(USER, disabled=["household"], role="admin"), "personal"
    )
    assert ("_household", "personal") not in stores_disabled


def test_allowed_stores_for_excludes_pool_for_non_admin(user_brain):
    """2026-09-05 owner ask: pool trash is an admin-only tab — a non-admin
    only ever sees their own personal store, regardless of module state."""
    stores = trash_service.allowed_stores_for(_user_dict(USER, role="member"), "personal")
    assert stores == [(USER, "personal")]


def test_list_trash_for_user_tags_scope(user_brain):
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)

    admin_entries = trash_service.list_trash_for_user(_user_dict(USER, role="admin"), "personal")
    mine = next(e for e in admin_entries if e["original_id"] == task["id"])
    assert mine["scope"] == "personal"
