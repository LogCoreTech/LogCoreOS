"""Tests for the Automation Inbox — routing, dedup, review gating, notifications."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import HTTPException

from services import auth_service
from services import automation_inbox_service as svc
from services import automations_config, suggestions_service


@pytest.fixture()
def users(brain):
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def _post_items(user, workflow_key, items, workspace="business"):
    from routers.automations import AutomationInboxPost, InboxItemIn, automation_post_items

    return automation_post_items(
        AutomationInboxPost(
            user=user,
            workspace=workspace,
            workflow_key=workflow_key,
            items=[InboxItemIn(**i) for i in items],
        ),
        _auth=None,
        _rl=None,
    )


def _set_status(item_id, status, user, workspace="business", note=None):
    from routers.automations import ItemStatusUpdate, set_item_status

    return set_item_status(
        item_id,
        ItemStatusUpdate(status=status, note=note),
        current_user=user,
        workspace=workspace,
        _rl=None,
    )


LEAD = {"external_id": "listing-1", "title": "12 ac — Bastrop — $89k", "fields": {"price": 89000}}
LEAD2 = {"external_id": "listing-2", "title": "40 ac — Hays — $210k", "url": "https://x.example"}


# ---------------------------------------------------------------------------
# Posting, routing, dedup
# ---------------------------------------------------------------------------


def test_post_routes_to_claiming_inbox(users):
    box = svc.create_inbox("_team", "Land Leads", workflows=["land-lead-search"])
    result = _post_items("_team", "land-lead-search", [LEAD, LEAD2])
    assert result == {"created": 2, "skipped": 0, "inbox_id": box["id"]}
    items = svc.load_store("_team")["items"]
    assert all(i["inbox_id"] == box["id"] and i["status"] == "new" for i in items)


def test_unmapped_key_goes_to_general_created_once(users):
    _post_items("_team", "mystery-flow", [LEAD])
    _post_items("_team", "other-flow", [LEAD2])
    data = svc.load_store("_team")
    generals = [b for b in data["inboxes"] if b["name"] == svc.DEFAULT_INBOX_NAME]
    assert len(generals) == 1
    assert all(i["inbox_id"] == generals[0]["id"] for i in data["items"])


def test_dedup_and_seen_endpoint(users):
    from routers.automations import automation_seen_ids

    _post_items("_team", "land-lead-search", [LEAD, LEAD2])
    result = _post_items("_team", "land-lead-search", [LEAD, LEAD2])
    assert result["created"] == 0 and result["skipped"] == 2
    seen = automation_seen_ids(user="_team", workflow_key="land-lead-search", _auth=None, _rl=None)
    assert sorted(seen["seen"]) == ["listing-1", "listing-2"]
    # Same external_id under a DIFFERENT workflow is a distinct item
    result = _post_items("_team", "another-flow", [LEAD])
    assert result["created"] == 1


def test_item_validation(users):
    with pytest.raises(HTTPException) as exc:
        _post_items("_team", "flow", [{"external_id": "  ", "title": "x"}])
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _post_items("unknown-user", "flow", [LEAD])
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Review gating + attribution
# ---------------------------------------------------------------------------


def test_reviewer_gating_and_attribution(users):
    svc.create_inbox("_team", "Land Leads", reviewers=["Bob"], workflows=["lead"])
    _post_items("_team", "lead", [LEAD])
    item_id = svc.load_store("_team")["items"][0]["id"]

    updated = _set_status(item_id, "interested", users["bob"], note="call the agent")
    assert updated["status"] == "interested"
    assert updated["status_by"] == "Bob" and updated["status_at"]
    assert updated["note"] == "call the agent"

    carol = auth_service.create_user("carol@example.com", "password123", "Carol")
    with pytest.raises(HTTPException) as exc:  # not a reviewer, not admin
        _set_status(item_id, "passed", carol)
    assert exc.value.status_code == 403
    # Admin always can
    assert _set_status(item_id, "closed", users["alice"])["status"] == "closed"


def test_personal_scope_owner_acts_and_manages(users):
    box = svc.create_inbox("Bob", "My Alerts", workflows=["price-watch"])
    _post_items("Bob", "price-watch", [LEAD], workspace="personal")
    item_id = svc.load_store("Bob")["items"][0]["id"]
    updated = _set_status(item_id, "interested", users["bob"], workspace="personal")
    assert updated["status_by"] == "Bob"
    # Owner manages their own personal inboxes without admin role
    from routers.automations import InboxUpdate, update_inbox

    renamed = update_inbox(
        box["id"],
        InboxUpdate(name="Watches"),
        current_user=users["bob"],
        workspace="personal",
        _rl=None,
    )
    assert renamed["name"] == "Watches"


def test_business_inbox_manage_is_admin_only(users):
    from routers.automations import InboxCreate, create_inbox

    with pytest.raises(HTTPException) as exc:
        create_inbox(
            InboxCreate(name="Nope"), current_user=users["bob"], workspace="business", _rl=None
        )
    assert exc.value.status_code == 403
    created = create_inbox(
        InboxCreate(name="Leads", reviewers=["Bob"]),
        current_user=users["alice"],
        workspace="business",
        _rl=None,
    )
    assert created["reviewers"] == ["Bob"]


def test_inbox_names_and_unknown_reviewers_validated(users):
    svc.create_inbox("_team", "Leads")
    with pytest.raises(ValueError, match="already exists"):
        svc.create_inbox("_team", "leads")
    with pytest.raises(ValueError, match="Unknown user"):
        svc.create_inbox("_team", "Other", reviewers=["Ghost"])


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def test_batch_notifies_recipients_once_with_open_inbox_action(users):
    box = svc.create_inbox("_team", "Land Leads", notify=["Bob"], workflows=["lead"])
    _post_items("_team", "lead", [LEAD, LEAD2])
    notifs = [
        n
        for n in suggestions_service.get_notifications("Bob")
        if n.get("action", {}).get("type") == "open_inbox"
    ]
    assert len(notifs) == 1  # one batched notification, not one per item
    assert notifs[0]["action"]["inbox_id"] == box["id"]
    assert notifs[0]["action"]["workspace"] == "business"
    assert "2 new items" in notifs[0]["title"]
    # No notify list → nobody pinged
    svc.create_inbox("_team", "Quiet", workflows=["silent"])
    _post_items("_team", "silent", [{"external_id": "q1", "title": "quiet"}])
    assert not any(
        n.get("action", {}).get("type") == "open_inbox"
        for n in suggestions_service.get_notifications("Alice")
    )


def test_personal_scope_notifies_owner_implicitly(users):
    _post_items("Bob", "price-watch", [LEAD], workspace="personal")
    assert any(
        n.get("action", {}).get("type") == "open_inbox" and n["action"]["workspace"] == "personal"
        for n in suggestions_service.get_notifications("Bob")
    )


# ---------------------------------------------------------------------------
# Retention + deletion
# ---------------------------------------------------------------------------


def test_trim_drops_oldest_reviewed_first(users):
    svc.create_inbox("_team", "Leads", workflows=["lead"], reviewers=["Bob"])
    items = [{"external_id": f"x{i}", "title": f"item {i}"} for i in range(svc.MAX_ITEMS_PER_SCOPE)]
    _post_items("_team", "lead", items[:100])
    _post_items("_team", "lead", items[100:200])
    # Review the first two so they become trim candidates
    store_items = svc.load_store("_team")["items"]
    svc.set_item_status("_team", store_items[0]["id"], "passed", by="Bob")
    svc.set_item_status("_team", store_items[1]["id"], "closed", by="Bob")
    # Fill to the cap and overflow by 2
    for chunk_start in range(200, svc.MAX_ITEMS_PER_SCOPE, 100):
        _post_items("_team", "lead", items[chunk_start : chunk_start + 100])
    _post_items(
        "_team",
        "lead",
        [{"external_id": "over1", "title": "o1"}, {"external_id": "over2", "title": "o2"}],
    )
    data = svc.load_store("_team")
    assert len(data["items"]) == svc.MAX_ITEMS_PER_SCOPE
    remaining_ids = {i["external_id"] for i in data["items"]}
    assert "x0" not in remaining_ids and "x1" not in remaining_ids  # reviewed dropped first
    assert {"over1", "over2"} <= remaining_ids


def test_inbox_delete_blocked_with_items_and_item_delete(users):
    box = svc.create_inbox("_team", "Leads", workflows=["lead"])
    _post_items("_team", "lead", [LEAD])
    with pytest.raises(ValueError, match="still has"):
        svc.delete_inbox("_team", box["id"])
    item_id = svc.load_store("_team")["items"][0]["id"]
    assert svc.delete_item("_team", item_id) is True
    assert svc.delete_inbox("_team", box["id"]) is True


# ---------------------------------------------------------------------------
# Token auth
# ---------------------------------------------------------------------------


def test_invalid_token_rejected(users):
    from routers.automations import _require_automation_token

    automations_config.get_api_token()  # ensure a token exists
    with pytest.raises(HTTPException) as exc:
        _require_automation_token("wrong-token")
    assert exc.value.status_code == 401
    _require_automation_token(automations_config.get_api_token())  # valid → no raise
