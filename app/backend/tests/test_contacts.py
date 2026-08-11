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
    # Only one self-contact ever exists for a user
    matches = [x for x in crm.list_contacts("Owner", "personal") if x.get("self_of") == "Owner"]
    assert len(matches) == 1


def test_get_self_contact_lazy_create(brain):
    assert crm.get_self_contact("Owner") is None
    created = crm.get_self_contact("Owner", create_if_missing=True)
    assert created is not None and created["self_of"] == "Owner"
    assert crm.get_self_contact("Owner") is not None  # now exists without create_if_missing


def test_get_self_contact_never_for_pool(brain):
    assert crm.get_self_contact("_household", create_if_missing=True) is None


def test_list_visible_contacts_pins_own_self_contact_first(brain):
    _contact(name="Zack the client")  # ordinary contact, created first
    self_c = crm.create_self_contact("Owner")
    visible = crm.list_visible_contacts("Owner", "member", False, "personal")
    assert visible[0]["id"] == self_c["id"]
    assert visible[0].get("_pinned") is True
    assert visible[0]["_access"] == "edit"
    # Never duplicated even though it also lives in Owner's own store
    assert sum(1 for v in visible if v["id"] == self_c["id"]) == 1


def test_list_visible_contacts_lazily_creates_self_contact(brain):
    visible = crm.list_visible_contacts("Owner", "member", False, "personal")
    assert any(v.get("self_of") == "Owner" for v in visible)


def test_self_contact_resolves_across_workspaces(brain):
    self_c = crm.create_self_contact("Owner")
    # find_contact in the BUSINESS workspace still resolves the personal-store self-contact
    found = crm.find_contact("Owner", "member", False, "business", self_c["id"])
    assert found is not None
    store_user, contact, access = found
    assert store_user == "Owner" and access == "edit"


def test_self_contact_pinned_only_in_own_list_not_others(brain):
    self_c = crm.create_self_contact("Owner")
    visible_to_worker = crm.list_visible_contacts("Worker", "member", False, "personal")
    assert not any(v["id"] == self_c["id"] for v in visible_to_worker)


def test_private_fields_stripped_for_non_owner_but_visible_to_owner(brain):
    self_c = crm.create_self_contact("Owner")
    crm.update_contact(
        "Owner", "personal", self_c["id"], {"conditions": "asthma", "income_range": "$100k+"}
    )
    crm.update_access(
        "Owner", "personal", self_c["id"], shared_with=[{"target": "Worker", "access": "read"}]
    )
    crm.respond_share("Worker", "Owner", "personal", self_c["id"], accept=True)

    owner_view = crm.find_contact("Owner", "member", False, "personal", self_c["id"])
    assert owner_view[1]["conditions"] == "asthma"

    worker_view = crm.find_contact("Worker", "member", False, "personal", self_c["id"])
    assert "conditions" not in worker_view[1]
    assert "income_range" not in worker_view[1]

    annotated = crm.annotate(owner_view[1], "Owner", "Worker", "read")
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
        crm.update_access("Owner", "personal", self_c["id"], hidden_from=["Owner"])


def test_admin_cannot_delete_archive_or_transfer_self_contact(brain):
    self_c = crm.create_self_contact("Owner")
    with pytest.raises(ValueError):
        crm.delete_contact("Owner", "personal", self_c["id"])
    with pytest.raises(ValueError):
        crm.set_archived("Owner", "personal", self_c["id"], True)
    with pytest.raises(ValueError):
        crm.transfer_ownership("Owner", "personal", self_c["id"], new_owner="Worker")
    # Untouched — still there, still not archived
    assert crm.get_contact("Owner", "personal", self_c["id"])["archived"] is False


def test_priority_order_workspace_keyed_validation(brain):
    self_c = crm.create_self_contact("Owner")
    updated = crm.update_contact(
        "Owner",
        "personal",
        self_c["id"],
        {"priority_order": {"personal": ["Health", "Family"], "business": ["Revenue"]}},
    )
    assert updated["priority_order"] == {"personal": ["Health", "Family"], "business": ["Revenue"]}
    with pytest.raises(ValueError):
        crm.update_contact(
            "Owner", "personal", self_c["id"], {"priority_order": ["not", "a", "dict"]}
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
    refreshed = crm.get_contact("Owner", "personal", self_c["id"])
    assert refreshed["affiliated_contact_ids"] == []


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
    self_c = crm.create_self_contact("Owner")
    with pytest.raises(ValueError):
        crm.update_access(
            "Owner", "personal", self_c["id"], shared_with=[{"target": "Worker", "access": "edit"}]
        )
    # read and contribute are still fine — nobody but the owner can ever edit,
    # but sharing basic info / allowing interactions+deals still works.
    rec, _ = crm.update_access(
        "Owner",
        "personal",
        self_c["id"],
        shared_with=[{"target": "Worker", "access": "contribute"}],
    )
    assert rec["shared_with"][0]["access"] == "contribute"


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
    crm.update_contact("Owner", "personal", self_c["id"], {"conditions": "none"})
    refreshed = crm.get_contact("Owner", "personal", self_c["id"])
    assert "## Health" in crm.format_profile_text(refreshed)
