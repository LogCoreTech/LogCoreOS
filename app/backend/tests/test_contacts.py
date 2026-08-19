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
    crm.update_contact(
        "Owner", "personal", c["id"], {"status": "lead", "phones": [{"number": "5551234567"}]}
    )
    got = crm.get_contact("Owner", "personal", c["id"])
    assert got["status"] == "lead"
    assert got["phones"] == [{"country_code": "1", "number": "5551234567", "extension": ""}]
    crm.set_archived("Owner", "personal", c["id"], True)
    assert crm.get_contact("Owner", "personal", c["id"])["archived"] is True


def test_phones_wrap_legacy_plain_strings(brain):
    c = _contact(name="Legacy")
    updated = crm.update_contact("Owner", "personal", c["id"], {"phones": ["555-123-4567"]})
    assert updated["phones"] == [{"country_code": "1", "number": "5551234567", "extension": ""}]


def test_phones_support_country_code_and_extension(brain):
    c = _contact(name="Intl")
    updated = crm.update_contact(
        "Owner",
        "personal",
        c["id"],
        {"phones": [{"country_code": "44", "number": "2079460958", "extension": "12"}]},
    )
    assert updated["phones"] == [{"country_code": "44", "number": "2079460958", "extension": "12"}]


def test_invalid_email_rejected(brain):
    c = _contact(name="Bad Email")
    with pytest.raises(ValueError):
        crm.update_contact("Owner", "personal", c["id"], {"emails": ["not-an-email"]})


def test_valid_email_accepted(brain):
    c = _contact(name="Good Email")
    updated = crm.update_contact("Owner", "personal", c["id"], {"emails": ["a@b.com"]})
    assert updated["emails"] == ["a@b.com"]


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


# --- Custom field person/company scoping (2026-08-15) -----------------------


def test_set_custom_fields_defaults_applies_to_both(brain):
    crm.set_custom_fields([{"key": "notes2", "label": "Notes 2", "type": "text"}])
    field = crm.get_custom_fields()[0]
    assert field["applies_to"] == ["company", "person"]


def test_set_custom_fields_respects_explicit_applies_to(brain):
    crm.set_custom_fields([{"key": "hq", "label": "HQ", "type": "text", "applies_to": ["company"]}])
    field = crm.get_custom_fields()[0]
    assert field["applies_to"] == ["company"]


def test_set_custom_fields_rejects_unknown_applies_to_values(brain):
    crm.set_custom_fields(
        [{"key": "x", "label": "X", "type": "text", "applies_to": ["bogus", "also-bogus"]}]
    )
    field = crm.get_custom_fields()[0]
    assert field["applies_to"] == ["company", "person"]  # invalid input falls back to both


def test_fields_for_type_filters_by_scope(brain):
    crm.set_custom_fields(
        [
            {"key": "hq", "label": "HQ", "type": "text", "applies_to": ["company"]},
            {"key": "hobby", "label": "Hobby", "type": "text", "applies_to": ["person"]},
            {
                "key": "notes2",
                "label": "Notes 2",
                "type": "text",
                "applies_to": ["person", "company"],
            },
        ]
    )
    person_keys = {f["key"] for f in crm.fields_for_type("person")}
    company_keys = {f["key"] for f in crm.fields_for_type("company")}
    assert person_keys == {"hobby", "notes2"}
    assert company_keys == {"hq", "notes2"}


def test_fields_for_type_treats_missing_applies_to_as_both(brain):
    # Simulates a definition written before applies_to existed.
    from services.file_service import contact_fields_path, write_json

    write_json(
        contact_fields_path(), {"fields": [{"key": "legacy", "label": "Legacy", "type": "text"}]}
    )
    assert "legacy" in {f["key"] for f in crm.fields_for_type("person")}
    assert "legacy" in {f["key"] for f in crm.fields_for_type("company")}


# --- Company vs. person fields (2026-08-14) ---------------------------------


def test_locations_and_hours_validation(brain):
    c = _contact(
        name="Acme Hardware",
        type="company",
        locations=[
            {"label": "Main St", "address": "123 Main St"},
            {"label": "", "address": ""},  # dropped — both blank
            {"label": "Warehouse", "address": "9 Industrial Way"},
        ],
        hours=[
            {"day": "mon", "open": "09:00", "close": "17:00"},
            {"day": "sat", "closed": True},
            {"day": "bogus", "open": "09:00", "close": "17:00"},  # dropped
        ],
    )
    assert len(c["locations"]) == 2
    assert c["locations"][0]["label"] == "Main St"
    assert {loc["id"] for loc in c["locations"]}  # ids assigned

    assert len(c["hours"]) == 7  # always all 7 days, in order
    assert [h["day"] for h in c["hours"]] == ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    mon = next(h for h in c["hours"] if h["day"] == "mon")
    assert mon == {"day": "mon", "open": "09:00", "close": "17:00", "closed": False}
    tue = next(h for h in c["hours"] if h["day"] == "tue")  # not provided -> defaults closed
    assert tue == {"day": "tue", "open": "", "close": "", "closed": True}
    sat = next(h for h in c["hours"] if h["day"] == "sat")
    assert sat["closed"] is True


def test_locations_cap_at_twenty(brain):
    many = [{"label": f"Branch {i}", "address": "x"} for i in range(30)]
    c = _contact(name="Big Chain", type="company", locations=many)
    assert len(c["locations"]) == 20


def test_person_fields_still_work_unaffected_by_company_fields(brain):
    c = _contact(
        name="Jane", type="person", gender="female", career_history=[{"title": "Engineer"}]
    )
    assert c["gender"] == "female"
    assert c["career_history"][0]["title"] == "Engineer"
    assert c["locations"] == []  # present, empty — same "always there" schema convention
    assert c["hours"] == []


def test_self_contact_cannot_be_switched_to_company(brain):
    self_c = crm.create_self_contact("Owner")
    assert self_c["type"] == "person"
    with pytest.raises(ValueError, match="must stay a person"):
        crm.update_contact(crm.POOL_HOUSEHOLD, "personal", self_c["id"], {"type": "company"})
    # Re-sending the same value (a no-op from the UI's own toggle) is fine.
    unchanged = crm.update_contact(crm.POOL_HOUSEHOLD, "personal", self_c["id"], {"type": "person"})
    assert unchanged["type"] == "person"


def test_ordinary_contact_can_still_change_type(brain):
    c = _contact(name="Ambiguous", type="person")
    updated = crm.update_contact("Owner", "personal", c["id"], {"type": "company"})
    assert updated["type"] == "company"


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


# --- Self-contact (Profile/Contacts merge) ---------------------------------


def test_create_self_contact_is_idempotent(brain):
    c1 = crm.create_self_contact("Owner", occupation="Electrician")
    c2 = crm.create_self_contact("Owner", occupation="Should be ignored")
    assert c1["id"] == c2["id"]
    assert c2["occupation"] == "Electrician"
    assert c2["self_of"] == "Owner"
    assert c2["cross_workspace"] is True
    # Only one self-contact ever exists for a user, and it lives in the
    # household pool (2026-08-17), not the user's own store.
    matches = [
        x for x in crm.list_contacts(crm.POOL_HOUSEHOLD, "personal") if x.get("self_of") == "Owner"
    ]
    assert len(matches) == 1
    assert crm.list_contacts("Owner", "personal") == []


def test_get_self_contact_lazy_create(brain):
    assert crm.get_self_contact("Owner") is None
    created = crm.get_self_contact("Owner", create_if_missing=True)
    assert created is not None and created["self_of"] == "Owner"
    assert crm.get_self_contact("Owner") is not None  # now exists without create_if_missing


def test_get_self_contact_never_for_pool(brain):
    assert crm.get_self_contact("_household", create_if_missing=True) is None


def test_list_visible_contacts_marks_own_self_contact_pinned(brain):
    # Ordering (pinning to the top) is a frontend concern now (Contacts.jsx
    # finds it by self_of and pins it client-side) — the backend just needs
    # to include it exactly once, correctly marked.
    _contact(name="Zack the client")
    self_c = crm.create_self_contact("Owner")
    visible = crm.list_visible_contacts("Owner", "member", False, "personal")
    mine = [v for v in visible if v["id"] == self_c["id"]]
    assert len(mine) == 1
    assert mine[0].get("_pinned") is True
    assert mine[0]["_access"] == "edit"
    assert "_owner" not in mine[0]


def test_list_visible_contacts_lazily_creates_self_contact(brain):
    visible = crm.list_visible_contacts("Owner", "member", False, "personal")
    assert any(v.get("self_of") == "Owner" for v in visible)


def test_self_contact_resolves_across_workspaces(brain):
    self_c = crm.create_self_contact("Owner")
    # find_contact in the BUSINESS workspace still resolves the household-pool self-contact
    found = crm.find_contact("Owner", "member", False, "business", self_c["id"])
    assert found is not None
    store_user, contact, access = found
    assert store_user == crm.POOL_HOUSEHOLD and access == "edit"
    assert crm.effective_workspace(store_user, contact, "business") == "personal"


def test_self_contact_visible_to_other_household_members_but_not_pinned_for_them(brain):
    # Owner item #3: "Each user's own contact permanently on both household
    # and team, everyone can find them." A household member other than the
    # owner now sees it too (it's an ordinary pool record from their
    # perspective) — just not marked _pinned, since that's self_of == viewer.
    self_c = crm.create_self_contact("Owner")
    visible_to_worker = crm.list_visible_contacts("Worker", "member", False, "personal")
    mine = [v for v in visible_to_worker if v["id"] == self_c["id"]]
    assert len(mine) == 1
    assert mine[0].get("_pinned") is not True
    assert mine[0]["_owner"] == "household"
    assert mine[0]["_access"] == "read"


def test_private_fields_stripped_for_non_owner_but_visible_to_owner(brain):
    self_c = crm.create_self_contact("Owner")
    crm.update_contact(
        crm.POOL_HOUSEHOLD,
        "personal",
        self_c["id"],
        {"conditions": "asthma", "income_range": "$100k+"},
    )
    # No explicit share/accept needed — it's a pool record, visible to every
    # household member by default (Worker included, per the fixture roster).

    owner_view = crm.find_contact("Owner", "member", False, "personal", self_c["id"])
    assert owner_view[1]["conditions"] == "asthma"

    worker_view = crm.find_contact("Worker", "member", False, "personal", self_c["id"])
    assert "conditions" not in worker_view[1]
    assert "income_range" not in worker_view[1]

    annotated = crm.annotate(owner_view[1], crm.POOL_HOUSEHOLD, "Worker", "read")
    assert "conditions" not in annotated


def test_private_fields_stripped_on_ordinary_shared_contact_too(brain):
    # The stripping rule is general (store_user == viewer), not self-contact-specific.
    c = _contact()
    c = crm.update_contact("Owner", "personal", c["id"], {"conditions": "n/a"})
    annotated = crm.annotate(c, "Owner", "Worker", "read")
    assert "conditions" not in annotated
    same_owner = crm.annotate(c, "Owner", "Owner", "edit")
    assert same_owner.get("conditions") == "n/a"


def test_hidden_from_can_never_include_self_contact_owner(brain):
    self_c = crm.create_self_contact("Owner")
    with pytest.raises(ValueError):
        crm.update_access(crm.POOL_HOUSEHOLD, "personal", self_c["id"], hidden_from=["Owner"])


def test_admin_cannot_delete_archive_or_transfer_self_contact(brain):
    self_c = crm.create_self_contact("Owner")
    with pytest.raises(ValueError):
        crm.delete_contact(crm.POOL_HOUSEHOLD, "personal", self_c["id"])
    with pytest.raises(ValueError):
        crm.set_archived(crm.POOL_HOUSEHOLD, "personal", self_c["id"], True)
    with pytest.raises(ValueError):
        crm.transfer_ownership(crm.POOL_HOUSEHOLD, "personal", self_c["id"], new_owner="Worker")
    # Untouched — still there, still not archived
    assert crm.get_contact(crm.POOL_HOUSEHOLD, "personal", self_c["id"])["archived"] is False


def test_priority_order_workspace_keyed_validation(brain):
    self_c = crm.create_self_contact("Owner")
    updated = crm.update_contact(
        crm.POOL_HOUSEHOLD,
        "personal",
        self_c["id"],
        {"priority_order": {"personal": ["Health", "Family"], "business": ["Revenue"]}},
    )
    assert updated["priority_order"] == {"personal": ["Health", "Family"], "business": ["Revenue"]}
    with pytest.raises(ValueError):
        crm.update_contact(
            crm.POOL_HOUSEHOLD, "personal", self_c["id"], {"priority_order": ["not", "a", "dict"]}
        )


def test_affiliated_contact_ids_never_settable_via_update_contact(brain):
    c = _contact()
    updated = crm.update_contact(
        "Owner", "personal", c["id"], {"affiliated_contact_ids": ["x", "y"]}
    )
    assert updated["affiliated_contact_ids"] == []


def test_self_of_never_settable_via_update_contact(brain):
    c = _contact()
    updated = crm.update_contact("Owner", "personal", c["id"], {"self_of": "Owner"})
    assert updated.get("self_of") is None


def test_link_and_unlink_affiliation_is_symmetric(brain):
    self_c = crm.create_self_contact("Owner")
    partner = _contact(name="Partner")
    a, b = crm.link_affiliation("Owner", "member", False, "personal", self_c["id"], partner["id"])
    assert partner["id"] in a["affiliated_contact_ids"]
    assert self_c["id"] in b["affiliated_contact_ids"]

    a2, b2 = crm.unlink_affiliation(
        "Owner", "member", False, "personal", self_c["id"], partner["id"]
    )
    assert partner["id"] not in a2["affiliated_contact_ids"]
    assert self_c["id"] not in b2["affiliated_contact_ids"]


def test_link_affiliation_requires_edit_on_both_ends(brain):
    self_c = crm.create_self_contact("Owner")
    other_self = crm.create_self_contact("Worker")
    with pytest.raises(ValueError):
        crm.link_affiliation("Owner", "member", False, "personal", self_c["id"], other_self["id"])


def test_link_affiliation_rejects_self_link(brain):
    self_c = crm.create_self_contact("Owner")
    with pytest.raises(ValueError):
        crm.link_affiliation("Owner", "member", False, "personal", self_c["id"], self_c["id"])


def test_delete_contact_strips_dangling_affiliation_refs(brain):
    self_c = crm.create_self_contact("Owner")
    partner = _contact(name="Partner")
    crm.link_affiliation("Owner", "member", False, "personal", self_c["id"], partner["id"])
    crm.delete_contact("Owner", "personal", partner["id"])
    refreshed = crm.get_contact(crm.POOL_HOUSEHOLD, "personal", self_c["id"])
    assert refreshed["affiliated_contact_ids"] == []


def test_core_values_stored_as_deduped_capped_list(brain):
    c = _contact(core_values=["Honesty", "Honesty", "  Growth  ", ""])
    assert c["core_values"] == ["Honesty", "Growth"]


def test_core_values_accepts_legacy_comma_string(brain):
    # The AI's update_contact/update_profile tools call update_contact()
    # directly with a raw fields dict, bypassing ContactUpdate's Pydantic
    # list[str] type entirely — nothing stops a plain string arriving here,
    # which would otherwise silently iterate into individual characters.
    c = _contact(core_values="Honesty, Growth,  Growth ")
    assert c["core_values"] == ["Honesty", "Growth"]


# --- Self-contact section hiding (2026-08-18, owner: "hiddeable for user
# contacts by the user themself only") -------------------------------------


def test_hidden_sections_strips_matching_fields_for_non_owner_but_visible_to_owner(brain):
    self_c = crm.create_self_contact("Owner")
    crm.update_contact(
        crm.POOL_HOUSEHOLD,
        "personal",
        self_c["id"],
        {
            "career_history": [{"title": "Engineer", "archived": False}],
            "address": "123 Main St",
            "hidden_sections": ["career", "address"],
        },
    )

    owner_view = crm.find_contact("Owner", "member", False, "personal", self_c["id"])
    assert owner_view[1]["career_history"][0]["title"] == "Engineer"
    assert owner_view[1]["address"] == "123 Main St"

    worker_view = crm.find_contact("Worker", "member", False, "personal", self_c["id"])
    assert "career_history" not in worker_view[1]
    assert "address" not in worker_view[1]
    # A section NOT in hidden_sections stays visible as normal.
    assert worker_view[1]["self_of"] == "Owner"


def test_hidden_sections_rejects_unknown_key(brain):
    self_c = crm.create_self_contact("Owner")
    with pytest.raises(ValueError, match="Unknown section"):
        crm.update_contact(
            crm.POOL_HOUSEHOLD, "personal", self_c["id"], {"hidden_sections": ["not_a_section"]}
        )


def test_update_contact_strips_hidden_sections_when_viewer_is_not_owner(brain):
    # Only the record's own owner may ever change what's hidden — mirrors
    # the identical _PRIVATE_FIELDS write-guard test above, same root cause
    # class (a third party must never be able to inject data the owner
    # alone controls), just for hidden_sections instead of a private field.
    self_c = crm.create_self_contact("Owner")
    crm.update_access(
        crm.POOL_HOUSEHOLD,
        "personal",
        self_c["id"],
        contributors=[{"target": "Worker", "access": "contribute"}],
    )
    updated = crm.update_contact(
        crm.POOL_HOUSEHOLD,
        "personal",
        self_c["id"],
        {"hidden_sections": ["career"]},
        viewer="Worker",
    )
    assert updated.get("hidden_sections") in (None, [])
    # The owner, acting as themselves, can still set it normally.
    updated2 = crm.update_contact(
        crm.POOL_HOUSEHOLD,
        "personal",
        self_c["id"],
        {"hidden_sections": ["career"]},
        viewer="Owner",
    )
    assert updated2["hidden_sections"] == ["career"]


def test_update_contact_strips_private_fields_when_viewer_is_not_owner(brain):
    # General write-guard, exercised on an ordinary (non-self) contact since
    # self-contacts can no longer be shared at edit level at all (see
    # test_self_contact_sharing_capped_below_edit).
    c = _contact(name="Ordinary")
    crm.update_access(
        "Owner", "personal", c["id"], shared_with=[{"target": "Worker", "access": "edit"}]
    )
    crm.respond_share("Worker", "Owner", "personal", c["id"], accept=True)
    # Worker has edit access but must never be able to inject private data,
    # even though they can't read it back themselves.
    updated = crm.update_contact(
        "Owner", "personal", c["id"], {"conditions": "sneaky"}, viewer="Worker"
    )
    assert updated.get("conditions") in (None, "")
    # The owner, acting as themselves, can still set it normally.
    updated2 = crm.update_contact(
        "Owner", "personal", c["id"], {"conditions": "asthma"}, viewer="Owner"
    )
    assert updated2["conditions"] == "asthma"


def test_self_contact_sharing_capped_below_edit(brain):
    # Self-contacts are pool records now, so this uses contributors, not
    # shared_with (shared_with is rejected outright on any pool contact —
    # see test_pool_contributors_and_admin).
    self_c = crm.create_self_contact("Owner")
    with pytest.raises(ValueError):
        crm.update_access(
            crm.POOL_HOUSEHOLD,
            "personal",
            self_c["id"],
            contributors=[{"target": "Worker", "access": "edit"}],
        )
    # read and contribute are still fine — nobody but the owner can ever edit,
    # but sharing basic info / allowing interactions+deals still works.
    rec, _ = crm.update_access(
        crm.POOL_HOUSEHOLD,
        "personal",
        self_c["id"],
        contributors=[{"target": "Worker", "access": "contribute"}],
    )
    assert rec["contributors"][0]["access"] == "contribute"


def test_gender_validation(brain):
    c = _contact(name="G")
    with pytest.raises(ValueError):
        crm.update_contact("Owner", "personal", c["id"], {"gender": "other"})
    updated = crm.update_contact("Owner", "personal", c["id"], {"gender": "female"})
    assert updated["gender"] == "female"


def test_height_weight_validation(brain):
    c = _contact(name="H")
    updated = crm.update_contact(
        "Owner",
        "personal",
        c["id"],
        {"height_cm": 180, "height_unit": "cm", "weight_kg": 75, "weight_unit": "kg"},
    )
    assert updated["height_cm"] == 180 and updated["weight_kg"] == 75
    with pytest.raises(ValueError):
        crm.update_contact("Owner", "personal", c["id"], {"height_cm": 999})
    with pytest.raises(ValueError):
        crm.update_contact("Owner", "personal", c["id"], {"height_unit": "miles"})


def test_blood_type_validation(brain):
    c = _contact(name="B")
    with pytest.raises(ValueError):
        crm.update_contact("Owner", "personal", c["id"], {"blood_type": "Z+"})
    updated = crm.update_contact("Owner", "personal", c["id"], {"blood_type": "O-"})
    assert updated["blood_type"] == "O-"


def test_time_field_validation(brain):
    c = _contact(name="T")
    updated = crm.update_contact("Owner", "personal", c["id"], {"wake_weekday": "06:30"})
    assert updated["wake_weekday"] == "06:30"
    with pytest.raises(ValueError):
        crm.update_contact("Owner", "personal", c["id"], {"bedtime": "not-a-time"})


def test_career_history_add_and_archive_flow(brain):
    c = _contact(name="Career")
    updated = crm.update_contact(
        "Owner",
        "personal",
        c["id"],
        {
            "career_history": [
                {
                    "title": "Junior Dev",
                    "education": "Bachelor's Degree",
                    "years_experience": "1-2",
                    "start_date": "2020-01",
                    "archived": False,
                }
            ]
        },
    )
    assert len(updated["career_history"]) == 1
    entry_id = updated["career_history"][0]["id"]
    # Archive it and add a new current role.
    updated2 = crm.update_contact(
        "Owner",
        "personal",
        c["id"],
        {
            "career_history": [
                {**updated["career_history"][0], "end_date": "2022-06", "archived": True},
                {"title": "Senior Dev", "start_date": "2022-06", "archived": False},
            ]
        },
    )
    assert len(updated2["career_history"]) == 2
    assert updated2["career_history"][0]["id"] == entry_id
    assert updated2["career_history"][0]["archived"] is True
    assert updated2["career_history"][1]["archived"] is False


def test_career_history_rejects_unknown_education(brain):
    c = _contact(name="Career2")
    with pytest.raises(ValueError):
        crm.update_contact(
            "Owner",
            "personal",
            c["id"],
            {"career_history": [{"title": "X", "education": "Made Up Degree"}]},
        )


def test_set_and_clear_contact_photo(brain):
    c = _contact(name="Photo")
    updated = crm.set_contact_photo("Owner", "personal", c["id"], "jpg")
    assert updated["photo_ext"] == "jpg"
    cleared = crm.clear_contact_photo("Owner", "personal", c["id"])
    assert cleared["photo_ext"] is None


def test_format_profile_text_includes_populated_sections_only(brain):
    self_c = crm.create_self_contact("Owner", occupation="Baker")
    text = crm.format_profile_text(self_c)
    assert "Baker" in text
    assert "## Health" not in text
    crm.update_contact(crm.POOL_HOUSEHOLD, "personal", self_c["id"], {"conditions": "none"})
    refreshed = crm.get_contact(crm.POOL_HOUSEHOLD, "personal", self_c["id"])
    assert "## Health" in crm.format_profile_text(refreshed)


# --- Cross-workspace contacts (2026-08-17) ----------------------------------


def test_cross_workspace_contact_visible_from_the_opposite_tab(brain):
    c = _contact(name="Dual", cross_workspace=True)
    visible_business = crm.list_visible_contacts("Owner", "member", False, "business")
    assert any(v["id"] == c["id"] for v in visible_business)
    found = crm.find_contact("Owner", "member", False, "business", c["id"])
    assert found is not None
    assert found[2] == "edit"


def test_ordinary_contact_not_visible_cross_workspace_by_default(brain):
    c = _contact(name="Personal Only")
    assert c["cross_workspace"] is False
    visible_business = crm.list_visible_contacts("Owner", "member", False, "business")
    assert not any(v["id"] == c["id"] for v in visible_business)
    assert crm.find_contact("Owner", "member", False, "business", c["id"]) is None


def test_effective_workspace_resolves_to_the_true_home_store(brain):
    personal_contact = _contact(name="Lives In Personal", cross_workspace=True)
    business_contact = _contact(name="Lives In Business", ws="business", cross_workspace=True)
    assert crm.effective_workspace("Owner", personal_contact, "business") == "personal"
    assert crm.effective_workspace("Owner", business_contact, "personal") == "business"
    # Non-cross_workspace contacts are unaffected — always the ambient workspace.
    plain = _contact(name="Plain")
    assert crm.effective_workspace("Owner", plain, "business") == "business"


def test_editing_a_cross_workspace_contact_from_the_other_tab_updates_the_same_record(brain):
    c = _contact(name="Dual Edit", cross_workspace=True)
    found = crm.find_contact("Owner", "member", False, "business", c["id"])
    store_user, contact, _access = found
    ws = crm.effective_workspace(store_user, contact, "business")
    crm.update_contact(store_user, ws, c["id"], {"status": "edited from business tab"})
    # No duplicate was created in the business store — it landed on the one
    # real record, still only reachable in its true home (personal).
    assert crm.get_contact("Owner", "business", c["id"]) is None
    updated = crm.get_contact("Owner", "personal", c["id"])
    assert updated["status"] == "edited from business tab"


def test_pool_contact_default_and_flipping_cross_workspace(brain):
    pool_c = crm.create_contact(
        "_household", "personal", {"name": "Family Vet", "cross_workspace": True}, "Owner"
    )
    visible_from_team = crm.list_visible_contacts("Owner", "member", False, "business")
    assert any(v["id"] == pool_c["id"] for v in visible_from_team)


# --- Pool contact creation opened to non-admins (2026-08-17) ----------------


def test_pool_contact_creator_gets_edit_not_just_read(brain):
    # Pool contact creation used to be admin-only; opened to any contacts-
    # module user (routers/contacts.py). The creator must be able to edit
    # what they made, same as creating a personal contact already implies —
    # without this, a non-admin creator would only get "read" like everyone
    # else in the pool.
    pool_c = crm.create_contact("_household", "personal", {"name": "Plumber"}, "Worker")
    access = _access("Worker", pool_c["id"])
    assert access == "edit"
    # A different, non-creator household member still only gets read by default.
    assert _access("Owner", pool_c["id"]) == "read"
    # Admins still always get edit regardless of who created it.
    assert _access("Owner", pool_c["id"], admin=True) == "edit"


# --- Security must-pass: household AND team/business pool viewers ----------


@pytest.mark.parametrize("viewer_workspace", ["personal", "business"])
def test_self_contact_private_fields_stripped_for_any_pool_viewer(brain, viewer_workspace):
    """Owner security ask: pool visibility must never leak a contact's
    sensitive data to other household/team members. Checked from BOTH the
    household angle (personal workspace) and the team/business angle
    (business workspace) — self-contacts are forced cross_workspace, so a
    business-only viewer reaches the same household-pool record via the
    opposite-pool scan, and must get the identical stripping, not a weaker
    path on that side."""
    self_c = crm.create_self_contact("Owner")
    crm.update_contact(
        crm.POOL_HOUSEHOLD,
        "personal",
        self_c["id"],
        {
            "conditions": "asthma",
            "medications": "inhaler",
            "income_range": "$100k+",
            "budget_style": "Frugal",
            "communication_style": "Concise",
            "blood_type": "O-",
        },
    )
    found = crm.find_contact("Worker", "member", False, viewer_workspace, self_c["id"])
    assert found is not None
    _store_user, contact, access = found
    assert access == "read"
    for key in sorted(crm._PRIVATE_FIELDS):
        assert key not in contact, f"{key!r} leaked to a non-owner pool viewer"

    # The owner, from either workspace, still sees everything and can update it.
    owner_found = crm.find_contact("Owner", "member", False, viewer_workspace, self_c["id"])
    assert owner_found[1]["conditions"] == "asthma"
    restored = crm.update_contact(
        crm.POOL_HOUSEHOLD, "personal", self_c["id"], {"conditions": "resolved"}, viewer="Owner"
    )
    assert restored["conditions"] == "resolved"


@pytest.mark.parametrize("viewer_workspace", ["personal", "business"])
def test_self_contact_hidden_sections_stripped_for_any_pool_viewer(brain, viewer_workspace):
    """Same must-pass shape as the private-fields test above, for the new
    owner-toggleable hidden_sections mechanism instead of the fixed
    _PRIVATE_FIELDS set — checked from both the household and team/business
    angle so there's no weaker path on either side."""
    self_c = crm.create_self_contact("Owner")
    crm.update_contact(
        crm.POOL_HOUSEHOLD,
        "personal",
        self_c["id"],
        {
            "core_values": ["Honesty"],
            "life_mission": "Build things",
            "hidden_sections": ["values_principles"],
        },
    )
    found = crm.find_contact("Worker", "member", False, viewer_workspace, self_c["id"])
    assert found is not None
    _store_user, contact, _access = found
    for key in crm._HIDEABLE_SECTIONS["values_principles"]:
        assert key not in contact, f"{key!r} leaked to a non-owner pool viewer"

    owner_found = crm.find_contact("Owner", "member", False, viewer_workspace, self_c["id"])
    assert owner_found[1]["core_values"] == ["Honesty"]


def test_hidden_from_blocks_a_specific_pool_viewer_from_a_self_contact(brain):
    self_c = crm.create_self_contact("Owner")
    crm.update_access(crm.POOL_HOUSEHOLD, "personal", self_c["id"], hidden_from=["Worker"])
    assert crm.find_contact("Worker", "member", False, "personal", self_c["id"]) is None
    # The owner's own access is never affected by a hidden_from entry that
    # doesn't name them.
    assert crm.find_contact("Owner", "member", False, "personal", self_c["id"])[2] == "edit"
    # An uninvolved household member is unaffected too.
    assert crm.find_contact("Spouse", "member", False, "personal", self_c["id"])[2] == "read"


# --- Concurrency (2026-08-17) ------------------------------------------------


def test_concurrent_self_contact_creation_does_not_lose_a_record(brain):
    """create_contact()'s atomic update_json() rewrite closes a real,
    newly-elevated race: every user's self-contact now appends to the SAME
    shared household-pool file instead of their own. Fire several concurrent
    create_self_contact() calls for DIFFERENT users and confirm every one
    survives — a plain list-then-save two-step would silently lose some of
    these under real concurrency (demonstrated for an analogous case in
    task_service.py, see docs/MEMORY.md)."""
    import threading

    names = [f"Concurrent{i}" for i in range(20)]
    errors = []

    def _create(name):
        try:
            crm.create_self_contact(name)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append((name, exc))

    threads = [threading.Thread(target=_create, args=(n,)) for n in names]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    household = crm.list_contacts(crm.POOL_HOUSEHOLD, "personal")
    survived = {c["self_of"] for c in household if c.get("self_of") in names}
    assert survived == set(names)


# --- Migration m013: move self-contacts into the household pool ------------


def test_m013_moves_existing_self_contact_and_its_data_into_household_pool(brain):
    from migrations.runner import m013_move_self_contacts_to_household_pool

    # Simulate a pre-2026-08-17 install: a self-contact living in the user's
    # OWN store (the old storage location), with an interaction, a deal, and
    # a photo file — plus a shared_with entry, which must convert to a
    # contributors entry on the way into the pool (matches
    # transfer_ownership()'s own pool-destination conversion).
    from services.file_service import contact_photo_path

    old_contact = crm.create_contact(
        "Migrate", "personal", {"name": "Migrate", "type": "person"}, created_by="Migrate"
    )
    contacts = crm.list_contacts("Migrate", "personal")
    for c in contacts:
        if c["id"] == old_contact["id"]:
            c["self_of"] = "Migrate"
            c["shared_with"] = [{"target": "Worker", "access": "read", "accepted": []}]
    crm._save_contacts("Migrate", "personal", contacts)
    crm.add_interaction("Migrate", "personal", old_contact["id"], {"summary": "hi"}, "Migrate")
    crm.add_deal("Migrate", "personal", old_contact["id"], {"title": "Deal"}, "Migrate")
    photo_path = contact_photo_path("Migrate", "personal", old_contact["id"], "jpg")
    photo_path.parent.mkdir(parents=True, exist_ok=True)
    photo_path.write_bytes(b"fake-jpeg-bytes")
    crm.set_contact_photo("Migrate", "personal", old_contact["id"], "jpg")

    m013_move_self_contacts_to_household_pool(brain)

    assert crm.list_contacts("Migrate", "personal") == []
    moved = crm.get_self_contact("Migrate")
    assert moved is not None
    assert moved["id"] == old_contact["id"]
    assert moved["cross_workspace"] is True
    assert moved["shared_with"] == []
    assert moved["contributors"] == [{"target": "Worker", "access": "read"}]
    assert len(crm.list_interactions(crm.POOL_HOUSEHOLD, "personal", old_contact["id"])) == 1
    assert len(crm.list_deals(crm.POOL_HOUSEHOLD, "personal", old_contact["id"])) == 1
    new_photo = contact_photo_path(crm.POOL_HOUSEHOLD, "personal", old_contact["id"], "jpg")
    assert new_photo.exists()
    assert not photo_path.exists()

    # Idempotent — a second run is a clean no-op (get_self_contact already
    # finds it in the household pool, so the per-user loop skips it).
    m013_move_self_contacts_to_household_pool(brain)
    assert len(crm.list_contacts(crm.POOL_HOUSEHOLD, "personal")) == 1


def test_m013_skips_users_with_no_self_contact(brain):
    from migrations.runner import m013_move_self_contacts_to_household_pool

    _contact(store="NoProfile", name="Just an ordinary contact")
    m013_move_self_contacts_to_household_pool(brain)  # must not raise
    assert crm.list_contacts(crm.POOL_HOUSEHOLD, "personal") == []


# --- Migration m014: core_values string -> list -----------------------------


def _force_core_values(store, workspace, contact_id, raw_value):
    """Simulate a pre-2026-08-17 record whose core_values is still the old
    plain string — bypasses _validate_core_values, which would otherwise
    normalize it before it ever reaches storage."""
    contacts = crm.list_contacts(store, workspace)
    for c in contacts:
        if c["id"] == contact_id:
            c["core_values"] = raw_value
    crm._save_contacts(store, workspace, contacts)


def test_m014_converts_string_core_values_to_list(brain):
    from migrations.runner import m014_core_values_to_list

    c = _contact(name="Legacy")
    _force_core_values("Owner", "personal", c["id"], "Honesty, Growth,  Growth ")

    m014_core_values_to_list(brain)

    converted = crm.get_contact("Owner", "personal", c["id"])
    assert converted["core_values"] == ["Honesty", "Growth"]


def test_m014_leaves_list_core_values_untouched(brain):
    from migrations.runner import m014_core_values_to_list

    c = _contact(name="AlreadyMigrated", core_values=["Honesty"])
    m014_core_values_to_list(brain)
    assert crm.get_contact("Owner", "personal", c["id"])["core_values"] == ["Honesty"]


def test_m014_covers_the_household_pool_store_too(brain):
    from migrations.runner import m014_core_values_to_list

    self_c = crm.create_self_contact("Owner")
    _force_core_values(crm.POOL_HOUSEHOLD, "personal", self_c["id"], "Family first")

    m014_core_values_to_list(brain)

    assert crm.get_self_contact("Owner")["core_values"] == ["Family first"]


# --- Linking an existing contact at account creation (owner item #4) -------


def test_link_self_contact_marks_an_existing_household_contact(brain):
    pool_c = crm.create_contact("_household", "personal", {"name": "Future User"}, "Owner")
    linked = crm.link_self_contact(pool_c["id"], "NewPerson")
    assert linked["self_of"] == "NewPerson"
    assert linked["cross_workspace"] is True
    assert linked["type"] == "person"
    assert crm.get_self_contact("NewPerson")["id"] == pool_c["id"]


def test_link_self_contact_rejects_already_linked_contact(brain):
    pool_c = crm.create_contact("_household", "personal", {"name": "Taken"}, "Owner")
    crm.link_self_contact(pool_c["id"], "FirstUser")
    with pytest.raises(ValueError, match="already linked"):
        crm.link_self_contact(pool_c["id"], "SecondUser")


def test_link_self_contact_rejects_unknown_contact(brain):
    with pytest.raises(ValueError, match="not found"):
        crm.link_self_contact("does-not-exist", "SomeUser")


def test_link_self_contact_downgrades_existing_edit_contributors(brain):
    pool_c = crm.create_contact("_household", "personal", {"name": "Had Edit"}, "Owner")
    crm.update_access(
        "_household",
        "personal",
        pool_c["id"],
        contributors=[{"target": "Worker", "access": "edit"}],
    )
    linked = crm.link_self_contact(pool_c["id"], "NewPerson")
    assert linked["contributors"][0]["access"] == "contribute"


# --- Account deletion releases the self-contact (owner item #4) ------------


def test_release_self_contact_clears_self_of_but_keeps_the_record(brain):
    self_c = crm.create_self_contact("Departing")
    crm.add_interaction(
        crm.POOL_HOUSEHOLD, "personal", self_c["id"], {"summary": "hi"}, "Departing"
    )
    crm.release_self_contact("Departing")
    released = crm.get_contact(crm.POOL_HOUSEHOLD, "personal", self_c["id"])
    assert released is not None
    assert released.get("self_of") is None
    assert released["cross_workspace"] is True  # least-surprise, stays as before
    assert len(crm.list_interactions(crm.POOL_HOUSEHOLD, "personal", self_c["id"])) == 1
    assert crm.get_self_contact("Departing") is None


def test_release_self_contact_is_a_no_op_when_none_exists(brain):
    crm.release_self_contact("NeverSetUp")  # must not raise


# --- Presence dot wiring (Item 9, wired up 2026-08-17) ----------------------


def test_annotate_marks_self_contact_online_status(brain):
    from services import presence_service

    self_c = crm.create_self_contact("Owner")
    annotated_before = crm.annotate(self_c, crm.POOL_HOUSEHOLD, "Worker", "read")
    assert annotated_before["_online"] is False
    assert annotated_before["_last_seen"] is None

    presence_service.record_presence("Owner")
    annotated_after = crm.annotate(self_c, crm.POOL_HOUSEHOLD, "Worker", "read")
    assert annotated_after["_online"] is True
    assert annotated_after["_last_seen"] is not None


def test_annotate_never_adds_online_field_to_an_ordinary_contact(brain):
    c = _contact(name="Not A User")
    annotated = crm.annotate(c, "Owner", "Owner", "edit")
    assert "_online" not in annotated
