"""Notes sharing: sidecar index, folder-cascade resolution, handshake, pool,
hidden_from, and path-traversal rejection."""

import pytest

from services import notes_index
from services import notes_service as notes


@pytest.fixture(autouse=True)
def users(brain, monkeypatch):
    from services import auth_service

    roster = [
        {"name": "Owner", "role": "admin", "workspaces": ["personal", "business"]},
        {"name": "Worker", "role": "member", "workspaces": ["personal", "business"]},
    ]
    monkeypatch.setattr(auth_service, "list_users", lambda: roster)
    return roster


def _acc(viewer, path, role="member", admin=False, store="Owner", ws="personal"):
    return notes.resolve_access(viewer, role, admin, store, ws, path)


def test_share_handshake_and_cascade(brain):
    notes.create_folder("Owner", "Projects", "personal")
    notes.create_note("Owner", "Projects/Plan", "hi", "personal")
    notes.update_access(
        "Owner", "personal", "Projects", shared_with=[{"target": "Worker", "access": "read"}]
    )
    # Hidden until accepted; folder share cascades to the child note
    assert _acc("Worker", "Projects/Plan") is None
    notes.respond_share("Worker", "Owner", "personal", "Projects", accept=True)
    assert _acc("Worker", "Projects") == "read"
    assert _acc("Worker", "Projects/Plan") == "read"  # cascade
    # Decline drops the by-name entry
    notes.respond_share("Worker", "Owner", "personal", "Projects", accept=False)
    assert _acc("Worker", "Projects/Plan") is None


def test_contribute_and_edit_levels(brain):
    notes.create_note("Owner", "Shared", "x", "personal")
    notes.update_access(
        "Owner", "personal", "Shared", shared_with=[{"target": "Worker", "access": "contribute"}]
    )
    notes.respond_share("Worker", "Owner", "personal", "Shared", accept=True)
    assert _acc("Worker", "Shared") == "contribute"


def test_hidden_from_beats_share(brain):
    notes.create_note("Owner", "Secret", "x", "personal")
    notes.update_access(
        "Owner",
        "personal",
        "Secret",
        shared_with=[{"target": "household", "access": "edit"}],
        hidden_from=["Worker"],
    )
    notes.respond_share("Worker", "Owner", "personal", "Secret", accept=True)
    assert _acc("Worker", "Secret") is None


def test_pool_notes_contributors(brain):
    notes.create_note("_household", "Chores", "x", "personal")
    assert _acc("Owner", "Chores", admin=True, store="_household") == "edit"
    assert _acc("Worker", "Chores", store="_household") == "read"
    notes.update_access(
        "_household",
        "personal",
        "Chores",
        contributors=[{"target": "Worker", "access": "contribute"}],
    )
    assert _acc("Worker", "Chores", store="_household") == "contribute"
    with pytest.raises(ValueError):
        notes.update_access(
            "_household", "personal", "Chores", shared_with=[{"target": "Worker", "access": "read"}]
        )


def test_list_visible_includes_shared(brain):
    notes_index.rebuild_share_index()
    notes.create_note("Owner", "Doc", "x", "personal")
    notes.update_access(
        "Owner", "personal", "Doc", shared_with=[{"target": "Worker", "access": "read"}]
    )
    notes.respond_share("Worker", "Owner", "personal", "Doc", accept=True)
    visible = notes.list_visible_notes("Worker", "member", False, "personal")
    shared = [i for i in visible if i.get("_owner") == "Owner" and i["path"] == "Doc"]
    assert shared and shared[0]["_access"] == "read"


def test_find_note_store_rejects_traversal(brain):
    with pytest.raises(ValueError):
        notes.find_note_store("Owner", "member", False, "personal", "../../etc/passwd")
