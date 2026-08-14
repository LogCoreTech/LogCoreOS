"""get_workspace()/get_current_user() — the X-Workspace header must never grant
a workspace beyond what the caller's own `workspaces` field actually entitles
them to. get_workspace() is called directly (not just the service layer)
since the entitlement check itself lives in this router-level dependency
chain, not in any service function.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.security import HTTPAuthorizationCredentials

from routers.auth import get_current_user, get_workspace
from services import auth_service


class _FakeRequest:
    cookies: dict = {}


def _bearer(user: dict) -> HTTPAuthorizationCredentials:
    token = auth_service.create_token(user)
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_workspace_header_cannot_exceed_entitlement(brain):
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    assert bob.get("workspaces", ["personal"]) == ["personal"]

    resolved = get_current_user(_FakeRequest(), _bearer(bob), x_workspace="business")

    assert resolved["_workspace"] == "personal"


def test_get_workspace_reflects_the_same_coerced_value(brain):
    """The actual dependency every router injects — must match, not just the
    internal _workspace field get_current_user happens to set."""
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    current_user = get_current_user(_FakeRequest(), _bearer(bob), x_workspace="business")

    assert get_workspace(current_user) == "personal"


def test_workspace_header_honored_when_actually_entitled(brain):
    carol = auth_service.create_user("carol@example.com", "password123", "Carol")
    auth_service.update_user(carol["id"], {"workspaces": ["personal", "business"]})
    carol = auth_service.get_user_by_id(carol["id"])

    resolved = get_current_user(_FakeRequest(), _bearer(carol), x_workspace="business")

    assert resolved["_workspace"] == "business"


def test_admins_are_granted_every_enabled_workspace_and_keep_business(brain):
    admin = auth_service.create_user("admin@example.com", "password123", "Admin", role="admin")

    resolved = get_current_user(_FakeRequest(), _bearer(admin), x_workspace="business")

    assert resolved["_workspace"] == "business"
