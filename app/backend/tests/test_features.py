"""Tests for feature roles: services/features_service.py + routers/features.py.

Router functions are imported and called directly (bypassing FastAPI's Depends
plumbing) rather than only testing the service layer, because the bug this file
guards against — role names not being case/whitespace-normalized consistently
between create and lookup — lives in the router's request handling, not in
features_service.py itself.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException

from routers.features import (
    CreateRoleRequest,
    FeatureRoleRequest,
    RoleModulesRequest,
    create_role,
    delete_role,
    set_user_feature_role,
    update_role,
    users_with_role,
)
from services import auth_service, features_service


def _admin(brain):
    return auth_service.create_user("admin@example.com", "password123", "Admin", role="admin")


def _member(brain):
    return auth_service.create_user("bob@example.com", "password123", "Bob", role="member")


# --- features_service.py --------------------------------------------------


def test_load_features_seeds_builtin_roles(brain):
    data = features_service.load_features()
    assert "member" in data["roles"]
    assert "guest" in data["roles"]


def test_get_effective_disabled_uses_role_map(brain):
    # "notes" needs to be explicitly installed here (2026-08-26, once notes/
    # converted into a real discovered module) — get_effective_disabled's
    # not-installed union would otherwise mask the role map's own explicit
    # True and land it in `disabled` for an unrelated reason, defeating the
    # actual thing this test checks. Same fix shape as household/team's own
    # placeholder swap during their conversion.
    from services import mod_store_service

    mod_store_service.mark_installed("notes", by="tester")
    features_service.save_features(
        {"roles": {"member": {"finance": True}, "cleaner": {"finance": False, "notes": True}}}
    )
    disabled = features_service.get_effective_disabled("cleaner", [], "personal")
    assert "finance" in disabled
    assert "notes" not in disabled


def test_get_effective_disabled_unknown_role_falls_back_to_member(brain):
    features_service.save_features({"roles": {"member": {"finance": False}}})
    disabled = features_service.get_effective_disabled("does-not-exist", [], "personal")
    assert "finance" in disabled


def test_get_effective_disabled_workspace_keyed_dict(brain):
    # "goals" (not "finance"/"team") deliberately — the one remaining
    # hardcoded CORE module id, never a module_packages/ discovery, so it
    # can never collide with get_effective_disabled()'s own not-installed
    # union the way a real converted-but-optional module id would (team's
    # own 2026-08-25 conversion made this assertion start failing for the
    # wrong reason the first time: "team" showed up disabled in BOTH
    # workspaces simply because this bare test brain never marks it
    # installed, unrelated to the per-user override merging this test
    # actually exercises — "finance" itself hit the identical issue when
    # IT converted 2026-08-28, forcing this same swap a second time).
    features_service.save_features({"roles": {"member": {}}})
    per_user = {"personal": ["journal"], "business": ["goals"]}
    assert "journal" in features_service.get_effective_disabled("member", per_user, "personal")
    assert "goals" in features_service.get_effective_disabled("member", per_user, "business")
    assert "goals" not in features_service.get_effective_disabled("member", per_user, "personal")


# --- routers/features.py — role CRUD ---------------------------------------


def test_create_role_normalizes_name(brain):
    admin = _admin(brain)
    result = create_role(CreateRoleRequest(name="  Cleaner  ", modules={}), admin)
    assert result["name"] == "cleaner"
    assert "cleaner" in features_service.load_features()["roles"]


def test_create_role_rejects_reserved_names(brain):
    with pytest.raises(ValueError):
        CreateRoleRequest(name="admin", modules={})


def test_create_role_rejects_duplicate(brain):
    admin = _admin(brain)
    create_role(CreateRoleRequest(name="cleaner", modules={}), admin)
    with pytest.raises(HTTPException) as exc:
        create_role(CreateRoleRequest(name="Cleaner", modules={}), admin)
    assert exc.value.status_code == 400


def test_update_role_accepts_mismatched_case(brain):
    """The actual reported bug: a role created as 'Cleaner' is stored as 'cleaner';
    editing it moments later using the as-typed case must not 404."""
    admin = _admin(brain)
    create_role(CreateRoleRequest(name="Cleaner", modules={"goals": True}), admin)
    result = update_role("Cleaner", RoleModulesRequest(modules={"goals": False}), admin)
    assert result["modules"]["goals"] is False


def test_delete_role_accepts_mismatched_case(brain):
    admin = _admin(brain)
    create_role(CreateRoleRequest(name="Nanny", modules={}), admin)
    delete_role("  Nanny  ", admin)
    assert "nanny" not in features_service.load_features()["roles"]


def test_delete_role_protects_builtin_roles(brain):
    admin = _admin(brain)
    with pytest.raises(HTTPException) as exc:
        delete_role("member", admin)
    assert exc.value.status_code == 400


# --- routers/features.py — assigning a role to a user ----------------------


def test_set_user_feature_role_end_to_end(brain):
    admin = _admin(brain)
    bob = _member(brain)
    create_role(CreateRoleRequest(name="cleaner", modules={}), admin)

    set_user_feature_role(bob["id"], FeatureRoleRequest(feature_role="cleaner"), admin)

    assert auth_service.get_user_by_id(bob["id"])["feature_role"] == "cleaner"


def test_set_user_feature_role_accepts_mismatched_case(brain):
    """Same bug as test_update_role_accepts_mismatched_case, but for the actual
    "assign this role to a user" step named in the original report."""
    admin = _admin(brain)
    bob = _member(brain)
    create_role(CreateRoleRequest(name="cleaner", modules={}), admin)

    set_user_feature_role(bob["id"], FeatureRoleRequest(feature_role="Cleaner"), admin)

    assert auth_service.get_user_by_id(bob["id"])["feature_role"] == "cleaner"


def test_set_user_feature_role_rejects_unknown_role(brain):
    admin = _admin(brain)
    bob = _member(brain)
    with pytest.raises(HTTPException) as exc:
        set_user_feature_role(bob["id"], FeatureRoleRequest(feature_role="does-not-exist"), admin)
    assert exc.value.status_code == 400


def test_set_user_feature_role_rejects_self_change(brain):
    admin = _admin(brain)
    with pytest.raises(HTTPException) as exc:
        set_user_feature_role(admin["id"], FeatureRoleRequest(feature_role="member"), admin)
    assert exc.value.status_code == 400


def test_admin_create_user_normalizes_feature_role(brain):
    """POST /admin/users takes a feature_role at creation time too (NewUser.jsx) — it
    should persist the same normalized key create_role would have stored, not a
    differently-cased string that then silently falls back to 'member' behavior."""
    from routers.auth import CreateUserRequest, admin_create_user

    admin = _admin(brain)
    create_role(CreateRoleRequest(name="cleaner", modules={}), admin)

    req = CreateUserRequest(
        email="carol@example.com", password="password123", name="Carol", feature_role="Cleaner"
    )
    created = admin_create_user(req, admin)

    assert auth_service.get_user_by_id(created["id"])["feature_role"] == "cleaner"


def test_users_with_role_lists_assignees(brain):
    admin = _admin(brain)
    bob = _member(brain)
    create_role(CreateRoleRequest(name="cleaner", modules={}), admin)
    set_user_feature_role(bob["id"], FeatureRoleRequest(feature_role="cleaner"), admin)

    assert users_with_role("cleaner", admin) == {"users": ["Bob"]}


def test_users_with_role_empty_when_unassigned(brain):
    admin = _admin(brain)
    create_role(CreateRoleRequest(name="cleaner", modules={}), admin)

    assert users_with_role("cleaner", admin) == {"users": []}


def test_users_with_role_normalizes_case(brain):
    admin = _admin(brain)
    bob = _member(brain)
    create_role(CreateRoleRequest(name="cleaner", modules={}), admin)
    set_user_feature_role(bob["id"], FeatureRoleRequest(feature_role="cleaner"), admin)

    assert users_with_role("Cleaner", admin) == {"users": ["Bob"]}
