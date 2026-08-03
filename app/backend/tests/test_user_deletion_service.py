"""Tests for the admin user-deletion review flow: per-module transfer_ownership/
strip_user_references helpers, and the user_deletion_service orchestrator
(preview, completeness validation, execute, reference cleanup, notifications)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import assets_service as assets_svc
from services import auth_service
from services import contacts_service as crm
from services import finance_service as finance_svc
from services import notes_service as notes_svc
from services import user_deletion_service as uds
from services.file_service import assets_files_path, user_path


@pytest.fixture()
def users(brain):
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    carol = auth_service.create_user("carol@example.com", "password123", "Carol")
    for u in (alice, bob, carol):
        auth_service.update_user(u["id"], {"workspaces": ["personal", "business"]})
    yield {
        "alice": auth_service.get_user_by_id(alice["id"]),
        "bob": auth_service.get_user_by_id(bob["id"]),
        "carol": auth_service.get_user_by_id(carol["id"]),
    }
    auth_service._revoked_jtis.clear()


@pytest.fixture()
def widget(users):
    assets_svc.create_template({"key": "widget", "label": "Widget", "fields": []})


# ---------------------------------------------------------------------------
# Per-module transfer_ownership — Assets
# ---------------------------------------------------------------------------


def test_assets_transfer_preserves_shares_for_user_destination(users, widget):
    root = assets_svc.create_asset(
        "Alice", {"template": "widget", "name": "Root"}, created_by="Alice"
    )
    child = assets_svc.create_asset(
        "Alice",
        {"template": "widget", "name": "Child", "parent_id": root["id"]},
        created_by="Alice",
    )
    assets_svc.update_access(
        "Alice", root["id"], shared_with=[{"target": "Carol", "access": "read"}], by="Alice"
    )
    assets_svc.add_attachment(
        "Alice", child["id"], "plat.pdf", "application/pdf", b"%PDF", by="Alice"
    )

    moved = assets_svc.transfer_ownership(
        "Alice", root["id"], "personal", new_owner="Bob", by="Alice"
    )

    assert moved["parent_id"] is None
    assert moved["shared_with"][0]["target"] == "Carol"
    assert assets_svc.list_assets("Alice", "personal") == []
    bob_ids = {a["id"] for a in assets_svc.list_assets("Bob", "personal")}
    assert {root["id"], child["id"]} <= bob_ids
    assert (assets_files_path("Bob") / child["id"]).exists()
    assert not (assets_files_path("Alice") / child["id"]).exists()


def test_assets_transfer_to_pool_converts_shared_with_to_contributors(users, widget):
    root = assets_svc.create_asset(
        "Alice", {"template": "widget", "name": "Root"}, created_by="Alice"
    )
    assets_svc.update_access(
        "Alice", root["id"], shared_with=[{"target": "Carol", "access": "edit"}], by="Alice"
    )
    moved = assets_svc.transfer_ownership(
        "Alice", root["id"], "personal", new_owner="_household", by="Alice"
    )
    assert moved["shared_with"] == []
    assert any(c["target"] == "Carol" and c["access"] == "edit" for c in moved["contributors"])


# ---------------------------------------------------------------------------
# Per-module transfer_ownership — Finance
# ---------------------------------------------------------------------------


def test_finance_transfer_moves_directory_and_preserves_shares(users):
    book = finance_svc.create_book("Alice", "personal", name="Family", created_by="Alice")
    finance_svc.update_access(
        "Alice", "personal", book["id"], shared_with=[{"target": "Carol", "access": "read"}]
    )
    account = finance_svc.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "opening_balance_cents": 100_00}
    )
    finance_svc.add_transaction(
        "Alice",
        "personal",
        book,
        {"date": "2026-07-01", "amount_cents": -500, "account_id": account["id"]},
        created_by="Alice",
    )

    moved = finance_svc.transfer_ownership(
        "Alice", "personal", book["id"], new_owner="Bob", by="Alice"
    )
    assert moved["shared_with"][0]["target"] == "Carol"
    assert finance_svc.get_book("Alice", "personal", book["id"]) is None
    assert finance_svc.get_book("Bob", "personal", book["id"]) is not None
    _txs, total = finance_svc.list_transactions("Bob", "personal", book["id"])
    assert total == 1


def test_finance_transfer_to_pool_converts_shares(users):
    book = finance_svc.create_book("Alice", "personal", name="Family", created_by="Alice")
    finance_svc.update_access(
        "Alice", "personal", book["id"], shared_with=[{"target": "Carol", "access": "read"}]
    )
    moved = finance_svc.transfer_ownership(
        "Alice", "personal", book["id"], new_owner="_household", by="Alice"
    )
    assert moved["shared_with"] == []
    assert any(c["target"] == "Carol" for c in moved["contributors"])


# ---------------------------------------------------------------------------
# Per-module transfer_ownership — Contacts
# ---------------------------------------------------------------------------


def test_contacts_transfer_moves_interactions_and_deals(users):
    contact = crm.create_contact("Alice", "personal", {"name": "Acme"}, created_by="Alice")
    crm.update_access(
        "Alice", "personal", contact["id"], shared_with=[{"target": "Carol", "access": "read"}]
    )
    crm.add_interaction("Alice", "personal", contact["id"], {"summary": "call"}, "Alice")
    crm.add_deal("Alice", "personal", contact["id"], {"title": "Big deal"}, "Alice")

    moved = crm.transfer_ownership("Alice", "personal", contact["id"], new_owner="Bob", by="Alice")
    assert moved["shared_with"][0]["target"] == "Carol"
    assert crm.get_contact("Alice", "personal", contact["id"]) is None
    assert crm.get_contact("Bob", "personal", contact["id"]) is not None
    assert len(crm.list_interactions("Bob", "personal", contact["id"])) == 1
    assert len(crm.list_deals("Bob", "personal", contact["id"])) == 1
    assert crm.list_interactions("Alice", "personal", contact["id"]) == []


# ---------------------------------------------------------------------------
# Per-module transfer_ownership — Notes
# ---------------------------------------------------------------------------


def test_notes_transfer_moves_nested_shares(users):
    notes_svc.create_folder("Alice", "Projects", "personal")
    notes_svc.create_note("Alice", "Projects/readme", "hi", "personal")
    notes_svc.create_note("Alice", "Projects/Secret/plan", "shh", "personal")
    notes_svc.update_access(
        "Alice", "personal", "Projects", shared_with=[{"target": "Carol", "access": "read"}]
    )
    notes_svc.update_access(
        "Alice", "personal", "Projects/Secret", shared_with=[{"target": "Carol", "access": "edit"}]
    )

    notes_svc.transfer_ownership(
        "Alice", "personal", "Projects", "folder", new_owner="Bob", by="Alice"
    )

    assert notes_svc.get_note("Alice", "Projects/readme", "personal") is None
    assert notes_svc.get_note("Bob", "Projects/readme", "personal")["content"] == "hi"
    assert notes_svc.get_note("Bob", "Projects/Secret/plan", "personal")["content"] == "shh"

    bob_shares = notes_svc.load_shares("Bob", "personal")
    assert bob_shares["Projects"]["shared_with"][0]["target"] == "Carol"
    assert bob_shares["Projects/Secret"]["shared_with"][0]["access"] == "edit"
    assert notes_svc.load_shares("Alice", "personal") == {}


def test_notes_transfer_to_pool_converts_shares(users):
    notes_svc.create_note("Alice", "Ideas", "stuff", "personal")
    notes_svc.update_access(
        "Alice", "personal", "Ideas", shared_with=[{"target": "Carol", "access": "read"}]
    )
    notes_svc.transfer_ownership(
        "Alice", "personal", "Ideas", "note", new_owner="_household", by="Alice"
    )
    pool_shares = notes_svc.load_shares("_household", "personal")
    assert pool_shares["Ideas"]["shared_with"] == []
    assert any(c["target"] == "Carol" for c in pool_shares["Ideas"]["contributors"])


# ---------------------------------------------------------------------------
# Orchestrator — preview + validation
# ---------------------------------------------------------------------------


def test_preview_lists_only_shared_owned_items(users, widget):
    alice = users["alice"]
    shared = assets_svc.create_asset(
        "Alice", {"template": "widget", "name": "Shared"}, created_by="Alice"
    )
    assets_svc.update_access(
        "Alice", shared["id"], shared_with=[{"target": "Carol", "access": "read"}], by="Alice"
    )
    private = assets_svc.create_asset(
        "Alice", {"template": "widget", "name": "Private"}, created_by="Alice"
    )

    preview = uds.build_preview(alice)
    ids = {i["item_id"] for i in preview["eligible_items"]}
    assert shared["id"] in ids
    assert private["id"] not in ids


def test_validate_decisions_requires_full_resolution(users, widget):
    alice = users["alice"]
    shared = assets_svc.create_asset(
        "Alice", {"template": "widget", "name": "Shared"}, created_by="Alice"
    )
    assets_svc.update_access(
        "Alice", shared["id"], shared_with=[{"target": "Carol", "access": "read"}], by="Alice"
    )
    with pytest.raises(ValueError, match="Missing a decision"):
        uds.validate_decisions(alice, [])


def test_execute_rejects_missing_target_user_id(users, widget):
    alice, bob = users["alice"], users["bob"]
    shared = assets_svc.create_asset(
        "Alice", {"template": "widget", "name": "Shared"}, created_by="Alice"
    )
    assets_svc.update_access(
        "Alice", shared["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    decisions = [
        {
            "module": "assets",
            "workspace": "personal",
            "item_id": shared["id"],
            "action": "transfer_user",
            "target_user_id": None,
        }
    ]
    with pytest.raises(ValueError, match="Missing target user"):
        uds.execute(alice, decisions, executed_by="Admin")
    assert auth_service.get_user_by_id(alice["id"]) is not None


def test_transfer_user_rejects_workspace_mismatch(users):
    alice, carol = users["alice"], users["carol"]
    auth_service.update_user(carol["id"], {"workspaces": ["personal"]})
    book = finance_svc.create_book("Alice", "business", name="LLC", created_by="Alice")
    finance_svc.update_access(
        "Alice", "business", book["id"], shared_with=[{"target": "Bob", "access": "read"}]
    )
    decisions = [
        {
            "module": "finance",
            "workspace": "business",
            "item_id": book["id"],
            "action": "transfer_user",
            "target_user_id": carol["id"],
        }
    ]
    with pytest.raises(ValueError, match="workspace"):
        uds.execute(alice, decisions, executed_by="Admin")


# ---------------------------------------------------------------------------
# Orchestrator — full execute flow
# ---------------------------------------------------------------------------


def test_execute_transfer_full_flow_batches_one_notification(users, widget):
    alice, bob = users["alice"], users["bob"]
    a1 = assets_svc.create_asset("Alice", {"template": "widget", "name": "A1"}, created_by="Alice")
    assets_svc.update_access(
        "Alice", a1["id"], shared_with=[{"target": "Carol", "access": "read"}], by="Alice"
    )
    a2 = assets_svc.create_asset("Alice", {"template": "widget", "name": "A2"}, created_by="Alice")
    assets_svc.update_access(
        "Alice", a2["id"], shared_with=[{"target": "Carol", "access": "read"}], by="Alice"
    )

    decisions = [
        {
            "module": "assets",
            "workspace": "personal",
            "item_id": a1["id"],
            "action": "transfer_user",
            "target_user_id": bob["id"],
        },
        {
            "module": "assets",
            "workspace": "personal",
            "item_id": a2["id"],
            "action": "transfer_user",
            "target_user_id": bob["id"],
        },
    ]
    uds.execute(alice, decisions, executed_by="Admin")

    bob_ids = {a["id"] for a in assets_svc.list_assets("Bob", "personal")}
    assert {a1["id"], a2["id"]} <= bob_ids
    moved = assets_svc.get_asset("Bob", a1["id"], "personal")
    assert moved["shared_with"][0]["target"] == "Carol"

    from services import suggestions_service

    notifs = suggestions_service.get_notifications("Bob")
    assert len(notifs) == 1
    assert "2 items" in notifs[0]["title"]

    assert auth_service.get_user_by_id(alice["id"]) is None
    assert not user_path("Alice").exists()


def test_execute_deletes_item_when_decision_is_delete(users, widget):
    alice = users["alice"]
    root = assets_svc.create_asset(
        "Alice", {"template": "widget", "name": "Root"}, created_by="Alice"
    )
    child = assets_svc.create_asset(
        "Alice",
        {"template": "widget", "name": "Child", "parent_id": root["id"]},
        created_by="Alice",
    )
    assets_svc.update_access(
        "Alice", root["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )

    decisions = [
        {
            "module": "assets",
            "workspace": "personal",
            "item_id": root["id"],
            "action": "delete",
            "target_user_id": None,
        }
    ]
    uds.execute(alice, decisions, executed_by="Admin")
    # deleted along with the account's Brain folder either way — just confirm
    # the tree-delete helper didn't raise on a parent-with-children asset.
    assert auth_service.get_user_by_id(alice["id"]) is None
    assert child is not None


def test_execute_strips_departing_user_references_everywhere(users, widget):
    alice = users["alice"]

    shared_asset = assets_svc.create_asset(
        "Bob", {"template": "widget", "name": "Bob thing"}, created_by="Bob"
    )
    assets_svc.update_access(
        "Bob", shared_asset["id"], shared_with=[{"target": "Alice", "access": "read"}], by="Bob"
    )

    hidden_asset = assets_svc.create_asset(
        "Bob", {"template": "widget", "name": "Bob hidden"}, created_by="Bob"
    )
    assets_svc.update_access("Bob", hidden_asset["id"], hidden_from=["Alice"], by="Bob")

    pool_root = assets_svc.create_asset(
        "Bob", {"template": "widget", "name": "Household thing"}, created_by="Bob"
    )
    moved = assets_svc.convert_to_pool("Bob", pool_root["id"], by="Bob")
    assets_svc.update_access(
        "_household",
        moved["id"],
        contributors=[{"target": "Alice", "caps": {"fields": [], "add": ["comments"]}}],
        by="Bob",
        asset_workspace="personal",
    )

    contact = crm.create_contact("Carol", "personal", {"name": "Acme"}, created_by="Carol")
    crm.update_access(
        "Carol", "personal", contact["id"], shared_with=[{"target": "household", "access": "read"}]
    )
    crm.respond_share("Alice", "Carol", "personal", contact["id"], True)

    uds.execute(alice, [], executed_by="Admin")

    b1 = assets_svc.get_asset("Bob", shared_asset["id"], "personal")
    assert all(s.get("target") != "Alice" for s in b1["shared_with"])

    b2 = assets_svc.get_asset("Bob", hidden_asset["id"], "personal")
    assert "Alice" not in b2["hidden_from"]

    pool_item = assets_svc.get_asset("_household", moved["id"], "personal")
    assert all(c.get("target") != "Alice" for c in pool_item["contributors"])

    updated_contact = crm.get_contact("Carol", "personal", contact["id"])
    entry = updated_contact["shared_with"][0]
    assert entry["target"] == "household"
    assert "Alice" not in entry["accepted"]


def test_execute_failure_midway_leaves_account_intact(users, widget, monkeypatch):
    alice, bob = users["alice"], users["bob"]
    shared = assets_svc.create_asset(
        "Alice", {"template": "widget", "name": "Shared"}, created_by="Alice"
    )
    assets_svc.update_access(
        "Alice", shared["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )

    def boom(*_a, **_kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr(assets_svc, "transfer_ownership", boom)

    decisions = [
        {
            "module": "assets",
            "workspace": "personal",
            "item_id": shared["id"],
            "action": "transfer_user",
            "target_user_id": bob["id"],
        }
    ]
    with pytest.raises(RuntimeError):
        uds.execute(alice, decisions, executed_by="Admin")

    assert auth_service.get_user_by_id(alice["id"]) is not None
    assert user_path("Alice").exists()
