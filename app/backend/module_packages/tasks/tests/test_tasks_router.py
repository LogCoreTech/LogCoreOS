"""Router-level tests for module_packages/tasks/backend/router.py — the
first-ever HTTP-layer coverage of this router (task_service.py's own CRUD
logic is already covered by tests/test_task_service.py; this file is about
the router's own body logic, currently just the UX Polish Batch #4
bulk-delete endpoint).

Endpoint functions are called directly with a pre-resolved user dict and a
plain workspace string, matching this test suite's established convention
(see test_notes_router.py/test_assets_router.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from module_packages.tasks.backend.router import (
    BulkDeleteRequest,
    TaskCreate,
    add_task,
    bulk_delete_tasks,
)
from services import task_service


@pytest.fixture()
def users(brain):
    from services import auth_service

    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    yield {"alice": alice}
    auth_service._revoked_jtis.clear()


def _make(title="Task", category="Work"):
    return TaskCreate(title=title, category=category)


def test_bulk_delete_success(users):
    a = add_task(_make("A"), users["alice"], "personal")
    b = add_task(_make("B"), users["alice"], "personal")

    result = bulk_delete_tasks(
        BulkDeleteRequest(ids=[a["id"], b["id"]]), users["alice"], "personal"
    )

    assert set(result["deleted"]) == {a["id"], b["id"]}
    assert result["failed"] == []
    assert task_service.get_task("Alice", a["id"]) is None
    assert task_service.get_task("Alice", b["id"]) is None


def test_bulk_delete_reports_partial_failure(users):
    a = add_task(_make("A"), users["alice"], "personal")

    result = bulk_delete_tasks(
        BulkDeleteRequest(ids=[a["id"], "not-a-uuid", "11111111-1111-1111-1111-111111111111"]),
        users["alice"],
        "personal",
    )

    assert result["deleted"] == [a["id"]]
    errors = {f["id"]: f["error"] for f in result["failed"]}
    assert errors["not-a-uuid"] == "Invalid task ID format"
    assert errors["11111111-1111-1111-1111-111111111111"] == "Task not found"


def test_bulk_delete_lands_in_trash(users):
    a = add_task(_make("Trashed"), users["alice"], "personal")

    bulk_delete_tasks(BulkDeleteRequest(ids=[a["id"]]), users["alice"], "personal")

    from services import trash_service

    entries = trash_service.list_trash_for_user(
        {"name": "Alice", "disabled_modules": []}, "personal"
    )
    assert any(e["original_id"] == a["id"] for e in entries)
