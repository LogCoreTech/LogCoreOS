"""GET/PUT /brain/files/{path} must resolve inside the caller's active
workspace, not always the personal one — found 2026-08-22 via a real "Failed
to load that chat" report: Chat.jsx's openSession() reads a saved
conversation through this same endpoint, and any chat held in the business
workspace 404'd every time because the router ignored X-Workspace entirely
and always resolved against user_path() (personal-only). See docs/MEMORY.md
for the full mechanism.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException

from routers import brain
from services import auth_service
from services.file_service import ws_path, write_markdown


@pytest.fixture()
def dual_workspace_user(brain):
    user = auth_service.create_user("carol@example.com", "password123", "Carol")
    auth_service.update_user(user["id"], {"workspaces": ["personal", "business"]})
    return auth_service.get_user_by_id(user["id"])


def test_get_file_resolves_in_the_business_workspace(dual_workspace_user):
    business_dir = ws_path(dual_workspace_user["name"], "business") / "Chats"
    business_dir.mkdir(parents=True, exist_ok=True)
    write_markdown(business_dir / "convo.md", "# Business chat\n\n**You**: hi\n")

    result = brain.get_file("Chats/convo.md", dual_workspace_user, workspace="business")

    assert result["content"] == "# Business chat\n\n**You**: hi\n"


def test_get_file_in_business_workspace_is_not_visible_from_personal(dual_workspace_user):
    business_dir = ws_path(dual_workspace_user["name"], "business") / "Chats"
    business_dir.mkdir(parents=True, exist_ok=True)
    write_markdown(business_dir / "convo.md", "# Business chat\n\n**You**: hi\n")

    with pytest.raises(HTTPException) as exc:
        brain.get_file("Chats/convo.md", dual_workspace_user, workspace="personal")
    assert exc.value.status_code == 404


def test_get_file_still_resolves_in_personal_workspace(dual_workspace_user):
    personal_dir = ws_path(dual_workspace_user["name"], "personal") / "Chats"
    personal_dir.mkdir(parents=True, exist_ok=True)
    write_markdown(personal_dir / "convo.md", "# Personal chat\n\n**You**: hi\n")

    result = brain.get_file("Chats/convo.md", dual_workspace_user, workspace="personal")

    assert result["content"] == "# Personal chat\n\n**You**: hi\n"


def test_list_files_is_scoped_to_the_active_workspace(dual_workspace_user):
    personal_dir = ws_path(dual_workspace_user["name"], "personal")
    business_dir = ws_path(dual_workspace_user["name"], "business")
    write_markdown(personal_dir / "Personal_Only.md", "personal")
    business_dir.mkdir(parents=True, exist_ok=True)
    write_markdown(business_dir / "Business_Only.md", "business")

    personal_listing = brain.list_files(dual_workspace_user, workspace="personal")
    business_listing = brain.list_files(dual_workspace_user, workspace="business")

    assert {f["name"] for f in personal_listing} == {"Personal_Only.md"}
    assert {f["name"] for f in business_listing} == {"Business_Only.md"}


def test_business_folder_never_leaks_into_a_personal_listing(dual_workspace_user):
    """ws_path()'s business base is a literal subfolder of the personal base
    on disk (brain/USERS/{name}/Business/), not a sibling — a naive recursive
    walk of personal would otherwise surface business files as if they were
    the user's own personal notes."""
    business_dir = ws_path(dual_workspace_user["name"], "business")
    business_dir.mkdir(parents=True, exist_ok=True)
    write_markdown(business_dir / "Business_Only.md", "business")

    personal_listing = brain.list_files(dual_workspace_user, workspace="personal")

    assert "Business_Only.md" not in {f["name"] for f in personal_listing}


def test_personal_workspace_cannot_path_traverse_into_business(dual_workspace_user):
    """Same nesting fact as above, but via direct path resolution rather than
    the listing endpoint: a personal-workspace GET for "Business/<file>" must
    not be able to reach the business file that genuinely exists there."""
    business_dir = ws_path(dual_workspace_user["name"], "business")
    business_dir.mkdir(parents=True, exist_ok=True)
    write_markdown(business_dir / "secret.md", "business-only content")

    with pytest.raises(HTTPException) as exc:
        brain.get_file("Business/secret.md", dual_workspace_user, workspace="personal")
    assert exc.value.status_code == 403


def test_save_file_writes_into_the_active_workspace(dual_workspace_user):
    business_dir = ws_path(dual_workspace_user["name"], "business") / "Chats"
    business_dir.mkdir(parents=True, exist_ok=True)
    write_markdown(business_dir / "convo.md", "original")

    brain.save_file(
        "Chats/convo.md",
        brain.SaveRequest(content="updated"),
        dual_workspace_user,
        workspace="business",
    )

    assert (business_dir / "convo.md").read_text() == "updated"
    personal_path = ws_path(dual_workspace_user["name"], "personal") / "Chats" / "convo.md"
    assert not personal_path.exists()
