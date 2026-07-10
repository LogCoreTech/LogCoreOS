"""Tests for Phase 2 — per-user templates, template sharing handshake, id refs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import assets_service as svc
from services import auth_service, suggestions_service


@pytest.fixture()
def users(brain):
    admin = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": admin}
    auth_service._revoked_jtis.clear()


def _tmpl(fields=None):
    return {"key": "parcel", "label": "Parcel", "fields": fields or []}


# ---------------------------------------------------------------------------
# Ownership & storage
# ---------------------------------------------------------------------------


def test_global_and_personal_templates_have_ids(users):
    g = svc.create_template(_tmpl(), owner=svc.GLOBAL_OWNER)
    p = svc.create_template({"key": "vehicle", "label": "Vehicle", "fields": []}, owner="Bob")
    assert g["id"] and p["id"] and g["id"] != p["id"]
    assert svc.get_template_by_id(g["id"])["owner"] == "_global"
    assert svc.get_template_by_id(p["id"])["owner"] == "Bob"


def test_personal_template_not_visible_to_others_until_shared(users):
    p = svc.create_template({"key": "vehicle", "fields": []}, owner="Bob")
    alice_keys = {t["id"] for t in svc.visible_templates("Alice", is_admin=True)}
    assert p["id"] not in alice_keys
    assert p["id"] in {t["id"] for t in svc.visible_templates("Bob")}


def test_same_key_across_owners_allowed(users):
    a = svc.create_template({"key": "parcel", "fields": []}, owner="Alice")
    b = svc.create_template({"key": "parcel", "fields": []}, owner="Bob")
    assert a["id"] != b["id"]


def test_duplicate_key_within_owner_rejected(users):
    svc.create_template({"key": "parcel", "fields": []}, owner="Bob")
    with pytest.raises(ValueError, match="already exists"):
        svc.create_template({"key": "parcel", "fields": []}, owner="Bob")


# ---------------------------------------------------------------------------
# restrict_roles on global templates
# ---------------------------------------------------------------------------


def test_restrict_roles_gates_global_template(users):
    g = svc.create_template(_tmpl(), owner=svc.GLOBAL_OWNER)
    svc.update_template(g["id"], {"restrict_roles": ["accountant"]})
    # member role can't see it; admin always can; accountant can
    assert g["id"] not in {t["id"] for t in svc.visible_templates("Bob", feature_role="member")}
    assert g["id"] in {t["id"] for t in svc.visible_templates("Bob", is_admin=True)}
    assert g["id"] in {t["id"] for t in svc.visible_templates("Bob", feature_role="accountant")}


# ---------------------------------------------------------------------------
# Template share handshake
# ---------------------------------------------------------------------------


def test_template_share_request_then_accept(users):
    p = svc.create_template({"key": "vehicle", "fields": []}, owner="Alice")
    svc.share_template("Alice", p["id"], [{"target": "Bob"}], by="Alice")
    # Pending — Bob can't use it yet, but got a notification
    assert p["id"] not in {t["id"] for t in svc.visible_templates("Bob")}
    assert any(
        n.get("action", {}).get("type") == "template_share"
        for n in suggestions_service.get_notifications("Bob")
    )
    svc.respond_to_template_share("Bob", {"owner": "Alice", "template_id": p["id"]}, True)
    shared = {t["id"]: t for t in svc.visible_templates("Bob")}
    assert p["id"] in shared and shared[p["id"]]["_scope"] == "shared"


def test_template_leave(users):
    p = svc.create_template({"key": "vehicle", "fields": []}, owner="Alice")
    svc.share_template("Alice", p["id"], [{"target": "Bob"}], by="Alice")
    svc.respond_to_template_share("Bob", {"owner": "Alice", "template_id": p["id"]}, True)
    assert p["id"] in {t["id"] for t in svc.visible_templates("Bob")}
    svc.leave_template_share("Bob", "Alice", p["id"])
    assert p["id"] not in {t["id"] for t in svc.visible_templates("Bob")}


def test_template_share_by_role_notifies_role_members(users):
    # Give Bob a custom role, share to it
    from services import features_service

    feats = features_service.load_features()
    feats.setdefault("roles", {})["accountant"] = feats["roles"]["member"].copy()
    features_service.save_features(feats)
    auth_service.update_user(
        auth_service.get_user_by_name("Bob")["id"], {"feature_role": "accountant"}
    )

    p = svc.create_template({"key": "ledger", "fields": []}, owner="Alice")
    svc.share_template("Alice", p["id"], [{"target": "accountant"}], by="Alice")
    assert any(
        n.get("action", {}).get("type") == "template_share"
        for n in suggestions_service.get_notifications("Bob")
    )


# ---------------------------------------------------------------------------
# id-based asset references + shared-asset resolution
# ---------------------------------------------------------------------------


def test_asset_stores_template_id_and_resolves(users):
    p = svc.create_template({"key": "vehicle", "label": "Vehicle", "fields": []}, owner="Alice")
    asset = svc.create_asset("Alice", {"template_id": p["id"], "name": "Truck"}, created_by="Alice")
    assert asset["template_id"] == p["id"]
    assert svc.resolve_template(asset)["id"] == p["id"]


def test_shared_asset_resolves_to_owners_personal_template(users):
    # A recipient can resolve an asset's template even though it's the OWNER's personal one.
    p = svc.create_template({"key": "vehicle", "label": "Vehicle", "fields": []}, owner="Alice")
    asset = svc.create_asset("Alice", {"template_id": p["id"], "name": "Truck"}, created_by="Alice")
    svc.update_access(
        "Alice", asset["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    svc.respond_to_asset_share(
        "Bob", {"owner": "Alice", "workspace": "personal", "asset_id": asset["id"]}, True
    )
    found = svc.find_asset("Bob", "personal", asset["id"])
    assert found is not None
    assert svc.resolve_template(found["asset"])["label"] == "Vehicle"


def test_legacy_asset_by_key_still_resolves(users):
    svc.create_template(_tmpl(), owner=svc.GLOBAL_OWNER)
    # Simulate a pre-Phase-2 asset: template key only, no template_id
    store = svc._load("Alice", "personal")
    store["assets"].append(
        {"id": "leg-1", "template": "parcel", "name": "Old", "parent_id": None, "fields": {}}
    )
    svc._save("Alice", "personal", store)
    asset = svc.get_asset("Alice", "leg-1")
    assert svc.resolve_template(asset)["key"] == "parcel"
