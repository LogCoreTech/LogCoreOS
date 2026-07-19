"""Contacts (CRM) module: CRUD, custom fields, pipeline, interactions, deals,
dedup, and asset-style sharing (handshake, specificity, hidden_from, pool)."""

import pytest

from services import contacts_index
from services import contacts_service as crm


@pytest.fixture(autouse=True)
def users(brain, monkeypatch):
    from services import auth_service

    roster = [
        {"name": "Owner", "role": "admin", "workspaces": ["personal", "business"]},
        {"name": "Worker", "role": "member", "workspaces": ["personal", "business"]},
        {"name": "Spouse", "role": "member", "workspaces": ["personal"]},
    ]
    monkeypatch.setattr(auth_service, "list_users", lambda: roster)
    return roster


def _contact(store="Owner", ws="personal", **kw):
    data = {"name": kw.pop("name", "Acme Co"), **kw}
    return crm.create_contact(store, ws, data, created_by=store)


def _access(viewer, contact_id, role="member", admin=False, ws="personal"):
    found = crm.find_contact(viewer, role, admin, ws, contact_id)
    return found[2] if found else None


# --- CRUD ------------------------------------------------------------------


def test_create_and_get(brain):
    c = _contact(name="Jane Doe", type="person", emails=["jane@x.com"], tags=["client"])
    assert c["name"] == "Jane Doe"
    assert c["emails"] == ["jane@x.com"]
    got = crm.get_contact("Owner", "personal", c["id"])
    assert got["id"] == c["id"]


def test_update_and_archive(brain):
    c = _contact(name="Bob")
    crm.update_contact("Owner", "personal", c["id"], {"status": "lead", "phones": ["555"]})
    got = crm.get_contact("Owner", "personal", c["id"])
    assert got["status"] == "lead" and got["phones"] == ["555"]
    crm.set_archived("Owner", "personal", c["id"], True)
    assert crm.get_contact("Owner", "personal", c["id"])["archived"] is True


def test_delete_cascades_interactions_and_deals(brain):
    c = _contact()
    crm.add_interaction("Owner", "personal", c["id"], {"summary": "hi"}, "Owner")
    crm.add_deal("Owner", "personal", c["id"], {"title": "Big deal"}, "Owner")
    assert crm.delete_contact("Owner", "personal", c["id"]) is True
    assert crm.list_interactions("Owner", "personal", c["id"]) == []
    assert crm.list_deals("Owner", "personal", c["id"]) == []


# --- Custom fields ---------------------------------------------------------


def test_custom_fields_validation(brain):
    crm.set_custom_fields(
        [
            {
                "key": "Lead Source",
                "label": "Lead Source",
                "type": "select",
                "options": ["Ref", "Ad"],
            },
            {"key": "score", "label": "Score", "type": "number"},
        ]
    )
    fields = crm.get_custom_fields()
    keys = {f["key"] for f in fields}
    assert "lead_source" in keys and "score" in keys
    c = _contact(custom={"score": "42", "lead_source": "Ref", "unknown": "x", "bad_select": "Nope"})
    assert c["custom"]["score"] == 42.0
    assert c["custom"]["lead_source"] == "Ref"
    assert "unknown" not in c["custom"]  # unknown key dropped


# --- Pipeline + deals ------------------------------------------------------


def test_pipeline_default_and_set(brain):
    assert crm.get_pipeline("Owner", "personal")[0] == "Lead"
    crm.set_pipeline("Owner", "personal", ["New", "Won", "Lost"])
    assert crm.get_pipeline("Owner", "personal") == ["New", "Won", "Lost"]


def test_deal_stage_validation_and_won(brain):
    c = _contact()
    d = crm.add_deal(
        "Owner",
        "personal",
        c["id"],
        {"title": "Sale", "value_cents": 5000, "stage": "Lead"},
        "Owner",
    )
    assert d["stage"] == "Lead" and not crm.is_won(d)
    d2 = crm.update_deal("Owner", "personal", d["id"], {"stage": "Won"})
    assert crm.is_won(d2)
    with pytest.raises(ValueError):
        crm.add_deal("Owner", "personal", c["id"], {"title": "X", "stage": "Nonsense"}, "Owner")


# --- Interactions + follow-ups ---------------------------------------------


def test_interactions_and_followups(brain):
    c = _contact()
    crm.add_interaction(
        "Owner",
        "personal",
        c["id"],
        {"type": "call", "summary": "called", "follow_up": "2026-01-01"},
        "Owner",
    )
    items = crm.list_interactions("Owner", "personal", c["id"])
    assert len(items) == 1 and items[0]["type"] == "call"
    due = crm.due_followups("Owner", "personal", "2026-06-01")
    assert any(x["kind"] == "interaction" for x in due)


# --- Dedup -----------------------------------------------------------------


def test_find_match_by_name_and_email(brain):
    c = _contact(name="Zeta LLC", emails=["z@zeta.com"])
    assert crm.find_match("Owner", "personal", name="zeta llc")["id"] == c["id"]
    assert crm.find_match("Owner", "personal", email="Z@ZETA.COM")["id"] == c["id"]
    assert crm.find_match("Owner", "personal", name="nobody") is None


# --- Sharing ---------------------------------------------------------------


def test_personal_share_requires_handshake(brain):
    c = _contact()
    _rec, notify = crm.update_access(
        "Owner", "personal", c["id"], shared_with=[{"target": "Worker", "access": "read"}]
    )
    assert "Worker" in notify
    # Not visible until accepted
    assert _access("Worker", c["id"]) is None
    crm.respond_share("Worker", "Owner", "personal", c["id"], accept=True)
    assert _access("Worker", c["id"]) == "read"
    # Decline drops the by-name entry
    crm.respond_share("Worker", "Owner", "personal", c["id"], accept=False)
    assert _access("Worker", c["id"]) is None


def test_by_name_overrides_group(brain):
    c = _contact()
    crm.update_access(
        "Owner",
        "personal",
        c["id"],
        shared_with=[
            {"target": "household", "access": "edit"},
            {"target": "Worker", "access": "read"},
        ],
    )
    crm.respond_share("Worker", "Owner", "personal", c["id"], accept=True)
    # by-name read overrides the household edit
    assert _access("Worker", c["id"]) == "read"


def test_hidden_from_beats_share(brain):
    c = _contact()
    crm.update_access(
        "Owner",
        "personal",
        c["id"],
        shared_with=[{"target": "household", "access": "edit"}],
        hidden_from=["Worker"],
    )
    crm.respond_share("Worker", "Owner", "personal", c["id"], accept=True)
    assert _access("Worker", c["id"]) is None


def test_pool_contributors_and_admin(brain):
    c = _contact(store="_household", ws="personal", name="Family Doctor")
    # Admin edits pool; plain member reads
    assert _access("Owner", c["id"], admin=True) == "edit"
    assert _access("Worker", c["id"]) == "read"
    # Contributor grant lifts a member to contribute
    crm.update_access(
        "_household",
        "personal",
        c["id"],
        contributors=[{"target": "Worker", "access": "contribute"}],
    )
    assert _access("Worker", c["id"]) == "contribute"
    # shared_with is rejected on pool contacts
    with pytest.raises(ValueError):
        crm.update_access(
            "_household", "personal", c["id"], shared_with=[{"target": "Worker", "access": "read"}]
        )


def test_share_index_routes_visibility(brain):
    contacts_index.rebuild_share_index()
    c = _contact()
    crm.update_access(
        "Owner", "personal", c["id"], shared_with=[{"target": "Worker", "access": "read"}]
    )
    crm.respond_share("Worker", "Owner", "personal", c["id"], accept=True)
    # Worker's visible list includes the shared contact via the index
    visible = crm.list_visible_contacts("Worker", "member", False, "personal")
    assert any(x["id"] == c["id"] for x in visible)


# --- Deal asset linking ----------------------------------------------------


def test_deal_link_unlink_asset_idempotent(brain):
    c = _contact()
    d = crm.add_deal("Owner", "personal", c["id"], {"title": "Job"}, "Owner")
    assert d["linked_asset_ids"] == []
    assert crm.link_asset("Owner", "personal", d["id"], "asset-1")["linked_asset_ids"] == [
        "asset-1"
    ]
    # Linking twice never duplicates
    assert crm.link_asset("Owner", "personal", d["id"], "asset-1")["linked_asset_ids"] == [
        "asset-1"
    ]
    assert crm.link_asset("Owner", "personal", d["id"], "asset-2")["linked_asset_ids"] == [
        "asset-1",
        "asset-2",
    ]
    assert crm.unlink_asset("Owner", "personal", d["id"], "asset-1")["linked_asset_ids"] == [
        "asset-2"
    ]
    # Unknown deal → None (router turns this into a 404)
    assert crm.link_asset("Owner", "personal", "nope", "x") is None
    assert crm.unlink_asset("Owner", "personal", "nope", "x") is None


def test_deal_linked_assets_survive_partial_update(brain):
    c = _contact()
    d = crm.add_deal("Owner", "personal", c["id"], {"title": "Job"}, "Owner")
    crm.link_asset("Owner", "personal", d["id"], "asset-1")
    updated = crm.update_deal("Owner", "personal", d["id"], {"title": "Renamed"})
    assert updated["linked_asset_ids"] == ["asset-1"]


def test_link_asset_on_legacy_deal_without_field(brain):
    """Deals created before asset linking have no linked_asset_ids key."""
    c = _contact()
    d = crm.add_deal("Owner", "personal", c["id"], {"title": "Old"}, "Owner")
    items = crm._list_deals("Owner", "personal")
    for it in items:
        it.pop("linked_asset_ids", None)
    crm._save_deals("Owner", "personal", items)
    updated = crm.link_asset("Owner", "personal", d["id"], "a1")
    assert updated["linked_asset_ids"] == ["a1"]


# --- Deal lookup by id (find_deal) ----------------------------------------


def test_find_deal_inherits_contact_access(brain):
    c = _contact()
    d = crm.add_deal("Owner", "personal", c["id"], {"title": "Job"}, "Owner")
    found = crm.find_deal("Owner", "member", False, "personal", d["id"])
    assert found is not None
    store, deal, contact, access = found
    assert store == "Owner" and deal["id"] == d["id"]
    assert contact["id"] == c["id"] and access == "edit"
    # Another user's personal deal stays invisible
    assert crm.find_deal("Worker", "member", False, "personal", d["id"]) is None


def test_find_deal_pool_readable_by_members(brain):
    pc = crm.create_contact("_household", "personal", {"name": "Pool Co"}, "Owner")
    pd = crm.add_deal("_household", "personal", pc["id"], {"title": "Pool job"}, "Owner")
    found = crm.find_deal("Worker", "member", False, "personal", pd["id"])
    assert found is not None
    assert found[3] == "read"
