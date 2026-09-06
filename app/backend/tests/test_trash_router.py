"""Tests for routers/trash.py — mirrors test_welcome_back_router.py's shape
(call the route function directly with real args, bypassing Depends)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException

from routers.trash import (
    BulkTrashRequest,
    TrashItemRequest,
    bulk_trash_action,
    list_trash,
    purge_entry,
    restore_entry,
)
from services import auth_service, task_service

USER = "TestUser"
OTHER = "OtherUser"


@pytest.fixture()
def alice(brain):
    user_dir = brain / "USERS" / USER / "Tasks"
    user_dir.mkdir(parents=True, exist_ok=True)
    return auth_service.create_user("alice@example.com", "password123", USER)


def _make_task(title="Test Task"):
    return {"title": title, "category": "Work", "priority": "High", "type": "todo"}


def test_list_trash_returns_deleted_task(alice):
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)

    result = list_trash(current_user=alice, workspace="personal")
    assert any(e["original_id"] == task["id"] for e in result)


def test_restore_entry_round_trip(alice):
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)
    entry = next(
        e
        for e in list_trash(current_user=alice, workspace="personal")
        if e["original_id"] == task["id"]
    )

    restored = restore_entry(
        TrashItemRequest(store_user=USER, entry_id=entry["id"]),
        current_user=alice,
        workspace="personal",
    )
    assert restored["id"] == task["id"]
    assert task_service.get_task(USER, task["id"]) is not None


def test_restore_entry_rejects_disallowed_store_user(alice):
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)
    entry = next(
        e
        for e in list_trash(current_user=alice, workspace="personal")
        if e["original_id"] == task["id"]
    )

    with pytest.raises(HTTPException) as exc_info:
        restore_entry(
            TrashItemRequest(store_user=OTHER, entry_id=entry["id"]),
            current_user=alice,
            workspace="personal",
        )
    assert exc_info.value.status_code == 403


def test_purge_entry_removes_permanently(alice):
    task = task_service.add_task(USER, _make_task())
    task_service.delete_task(USER, task["id"], deleted_by=USER)
    entry = next(
        e
        for e in list_trash(current_user=alice, workspace="personal")
        if e["original_id"] == task["id"]
    )

    result = purge_entry(
        TrashItemRequest(store_user=USER, entry_id=entry["id"]),
        current_user=alice,
        workspace="personal",
    )
    assert result == {"ok": True}
    assert not any(
        e["id"] == entry["id"] for e in list_trash(current_user=alice, workspace="personal")
    )


def test_purge_entry_404_when_missing(alice):
    with pytest.raises(HTTPException) as exc_info:
        purge_entry(
            TrashItemRequest(store_user=USER, entry_id="nonexistent"),
            current_user=alice,
            workspace="personal",
        )
    assert exc_info.value.status_code == 404


def test_bulk_action_reports_partial_failure(alice):
    task_a = task_service.add_task(USER, _make_task("A"))
    task_b = task_service.add_task(USER, _make_task("B"))
    task_service.delete_task(USER, task_a["id"], deleted_by=USER)
    task_service.delete_task(USER, task_b["id"], deleted_by=USER)
    entries = list_trash(current_user=alice, workspace="personal")
    entry_a = next(e for e in entries if e["original_id"] == task_a["id"])
    entry_b = next(e for e in entries if e["original_id"] == task_b["id"])

    result = bulk_trash_action(
        BulkTrashRequest(
            items=[
                TrashItemRequest(store_user=USER, entry_id=entry_a["id"]),
                TrashItemRequest(store_user=USER, entry_id="nonexistent"),
                TrashItemRequest(store_user=OTHER, entry_id=entry_b["id"]),
            ],
            action="purge",
        ),
        current_user=alice,
        workspace="personal",
    )

    results_by_id = {r["entry_id"]: r for r in result["results"]}
    assert results_by_id[entry_a["id"]]["ok"] is True
    assert results_by_id["nonexistent"]["ok"] is False
    assert results_by_id[entry_b["id"]]["ok"] is False
    assert results_by_id[entry_b["id"]]["error"] == "Access denied"


def test_bulk_action_rejects_invalid_action(alice):
    with pytest.raises(HTTPException) as exc_info:
        bulk_trash_action(
            BulkTrashRequest(items=[], action="delete_forever"),
            current_user=alice,
            workspace="personal",
        )
    assert exc_info.value.status_code == 400
