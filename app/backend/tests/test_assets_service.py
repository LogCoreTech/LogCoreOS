"""Tests for assets_service — templates, hierarchy, sharing, pools, attachments."""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import assets_index
from services import assets_service as svc
from services import auth_service, automations_config, task_service
from services.file_service import assets_files_path, user_path

PARCEL_FIELDS = [
    {
        "key": "status",
        "label": "Status",
        "type": "select",
        "options": ["available", "sold"],
        "default": "available",
    },
    {"key": "acreage", "label": "Acreage", "type": "number"},
    {"key": "county", "label": "County", "type": "text"},
    {"key": "close_date", "label": "Close Date", "type": "date"},
    {"key": "listed", "label": "Listed", "type": "boolean"},
]


@pytest.fixture()
def users(brain):
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


@pytest.fixture()
def parcel(users):
    svc.create_template({"key": "parcel", "label": "Parcel", "fields": PARCEL_FIELDS})
    svc.create_template({"key": "subdivision", "label": "Subdivision", "fields": []})
    return svc.get_template("parcel")


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def test_templates_start_empty(brain):
    assert svc.list_templates() == []


def test_create_and_get_template(users):
    svc.create_template({"key": "vehicle", "label": "Vehicle", "fields": []})
    assert svc.get_template("vehicle")["label"] == "Vehicle"


def test_duplicate_template_key_rejected(users):
    svc.create_template({"key": "vehicle", "fields": []})
    with pytest.raises(ValueError, match="already exists"):
        svc.create_template({"key": "vehicle", "fields": []})


def test_invalid_template_key_rejected(users):
    with pytest.raises(ValueError, match="Invalid template key"):
        svc.create_template({"key": "Bad Key!", "fields": []})


def test_select_field_requires_options(users):
    with pytest.raises(ValueError, match="needs at least one option"):
        svc.create_template(
            {"key": "x", "fields": [{"key": "status", "type": "select", "options": []}]}
        )


def test_field_order_preserved(parcel):
    keys = [f["key"] for f in svc.get_template("parcel")["fields"]]
    assert keys == ["status", "acreage", "county", "close_date", "listed"]


def test_update_template_replaces_fields(parcel):
    svc.update_template(parcel["id"], {"fields": [{"key": "acreage", "type": "number"}]})
    assert [f["key"] for f in svc.get_template("parcel")["fields"]] == ["acreage"]


def test_insert_example_uses_unique_keys(users):
    first = svc.insert_example_template()
    second = svc.insert_example_template()
    assert first["key"] == "example"
    assert second["key"] == "example_2"


def test_delete_template_blocked_when_referenced(parcel, users):
    svc.create_asset("Alice", {"template": "parcel", "name": "Lot 1"}, created_by="Alice")
    with pytest.raises(ValueError, match="still use template"):
        svc.delete_template(parcel["id"])


def test_delete_unused_template(parcel):
    sub_id = svc.get_template("subdivision")["id"]
    assert svc.delete_template(sub_id) is True
    assert svc.get_template("subdivision") is None


# ---------------------------------------------------------------------------
# Asset creation + field validation
# ---------------------------------------------------------------------------


def test_create_asset_prefills_defaults(parcel):
    asset = svc.create_asset("Alice", {"template": "parcel", "name": "Lot 1"}, created_by="Alice")
    assert asset["fields"]["status"] == "available"


def test_create_asset_unknown_template(users):
    with pytest.raises(ValueError, match="Unknown template"):
        svc.create_asset("Alice", {"template": "nope", "name": "X"}, created_by="Alice")


def test_create_asset_unknown_field_rejected(parcel):
    with pytest.raises(ValueError, match="Unknown field"):
        svc.create_asset(
            "Alice",
            {"template": "parcel", "name": "X", "fields": {"bogus": 1}},
            created_by="Alice",
        )


@pytest.mark.parametrize(
    "fields,match",
    [
        ({"acreage": "two"}, "must be a number"),
        ({"acreage": True}, "must be a number"),
        ({"county": 42}, "must be text"),
        ({"close_date": "07/04/2026"}, "YYYY-MM-DD"),
        ({"listed": "yes"}, "must be true or false"),
        ({"status": "pending"}, "must be one of"),
    ],
)
def test_field_type_validation(parcel, fields, match):
    with pytest.raises(ValueError, match=match):
        svc.create_asset(
            "Alice", {"template": "parcel", "name": "X", "fields": fields}, created_by="Alice"
        )


def test_empty_field_values_dropped(parcel):
    asset = svc.create_asset(
        "Alice",
        {"template": "parcel", "name": "X", "fields": {"county": "", "acreage": 2.5}},
        created_by="Alice",
    )
    assert "county" not in asset["fields"]
    assert asset["fields"]["acreage"] == 2.5


def test_update_merges_fields_and_null_deletes(parcel):
    asset = svc.create_asset(
        "Alice",
        {"template": "parcel", "name": "X", "fields": {"county": "Bexar", "acreage": 2.5}},
        created_by="Alice",
    )
    updated = svc.update_asset(
        "Alice", asset["id"], {"fields": {"acreage": None, "county": "Hill"}}, by="Alice"
    )
    assert "acreage" not in updated["fields"]
    assert updated["fields"]["county"] == "Hill"


def test_orphaned_value_survives_field_removal(parcel):
    asset = svc.create_asset(
        "Alice",
        {"template": "parcel", "name": "X", "fields": {"county": "Bexar"}},
        created_by="Alice",
    )
    svc.update_template(parcel["id"], {"fields": [{"key": "acreage", "type": "number"}]})
    current = svc.get_asset("Alice", asset["id"])
    assert current["fields"]["county"] == "Bexar"
    with pytest.raises(ValueError, match="Unknown field"):
        svc.update_asset("Alice", asset["id"], {"fields": {"county": "Hill"}}, by="Alice")
    cleared = svc.update_asset("Alice", asset["id"], {"fields": {"county": None}}, by="Alice")
    assert "county" not in cleared["fields"]


# ---------------------------------------------------------------------------
# Hierarchy, archive, delete
# ---------------------------------------------------------------------------


def _tree(users):
    sub = svc.create_asset("Alice", {"template": "subdivision", "name": "Sub"}, created_by="Alice")
    lot = svc.create_asset(
        "Alice",
        {"template": "parcel", "name": "Lot 1", "parent_id": sub["id"]},
        created_by="Alice",
    )
    return sub, lot


def test_parent_must_exist(parcel):
    with pytest.raises(ValueError, match="Parent asset"):
        svc.create_asset(
            "Alice",
            {"template": "parcel", "name": "X", "parent_id": "missing"},
            created_by="Alice",
        )


def test_cycle_rejected(parcel, users):
    sub, lot = _tree(users)
    with pytest.raises(ValueError, match="descendant"):
        svc.update_asset("Alice", sub["id"], {"parent_id": lot["id"]}, by="Alice")


def test_delete_blocked_with_children(parcel, users):
    sub, _ = _tree(users)
    with pytest.raises(ValueError, match="child asset"):
        svc.delete_asset("Alice", sub["id"])


def test_delete_leaf_removes_files_dir(parcel, users):
    _, lot = _tree(users)
    svc.add_attachment("Alice", lot["id"], "a.pdf", "application/pdf", b"%PDF", by="Alice")
    files_dir = assets_files_path("Alice") / lot["id"]
    assert files_dir.exists()
    assert svc.delete_asset("Alice", lot["id"]) is True
    assert not files_dir.exists()


def test_archive_only_this_node_leaves_children_active(parcel, users):
    # Per-node archive (no cascade): parent hidden, child stays active/visible.
    sub, lot = _tree(users)
    svc.set_archived("Alice", sub["id"], True, by="Alice")
    visible_ids = {a["id"] for a in svc.list_visible("Alice", "personal")}
    assert sub["id"] not in visible_ids
    assert lot["id"] in visible_ids  # child floats up, still active
    assert svc.get_asset("Alice", lot["id"])["archived"] is False


def test_archive_cascade_archives_whole_subtree(parcel, users):
    sub, lot = _tree(users)
    svc.set_archived("Alice", sub["id"], True, by="Alice", cascade=True)
    visible_ids = {a["id"] for a in svc.list_visible("Alice", "personal")}
    assert sub["id"] not in visible_ids and lot["id"] not in visible_ids
    assert svc.get_asset("Alice", lot["id"])["archived"] is True
    all_ids = {a["id"] for a in svc.list_visible("Alice", "personal", include_archived=True)}
    assert sub["id"] in all_ids and lot["id"] in all_ids


def test_can_delete_own_but_not_pool_or_shared(parcel, users):
    # Owner can delete own personal asset; a shared recipient cannot.
    lone = svc.create_asset("Alice", {"template": "parcel", "name": "Lone"}, created_by="Alice")
    assert svc.find_asset("Alice", "personal", lone["id"])["can_delete"] is True
    svc.update_access(
        "Alice", lone["id"], shared_with=[{"target": "Bob", "access": "edit"}], by="Alice"
    )
    svc.respond_to_asset_share(
        "Bob", {"owner": "Alice", "workspace": "personal", "asset_id": lone["id"]}, True
    )
    assert svc.find_asset("Bob", "personal", lone["id"])["can_delete"] is False
    # Pool asset: non-admin grantee cannot delete
    sub = svc.create_asset("Alice", {"template": "subdivision", "name": "S"}, created_by="Alice")
    svc.convert_to_pool("Alice", sub["id"], by="Alice")
    assert (
        svc.find_asset("Bob", "personal", sub["id"], pool_edit=["household"])["can_delete"] is False
    )
    assert svc.find_asset("Alice", "personal", sub["id"], is_admin=True)["can_delete"] is True


def test_count_active_descendants(parcel, users):
    sub, lot = _tree(users)
    assert svc.count_active_descendants("Alice", sub["id"]) == 1
    svc.set_archived("Alice", lot["id"], True, by="Alice")
    assert svc.count_active_descendants("Alice", sub["id"]) == 0


def test_unarchive_cascade(parcel, users):
    sub, lot = _tree(users)
    svc.set_archived("Alice", sub["id"], True, by="Alice", cascade=True)
    svc.set_archived("Alice", sub["id"], False, by="Alice", cascade=True)
    assert svc.get_asset("Alice", sub["id"])["archived"] is False
    assert svc.get_asset("Alice", lot["id"])["archived"] is False


def test_workspace_isolation(parcel):
    svc.create_asset(
        "Alice", {"template": "parcel", "name": "Biz Lot"}, workspace="business", created_by="Alice"
    )
    assert svc.list_assets("Alice", "personal") == []
    assert len(svc.list_assets("Alice", "business")) == 1


def test_history_recorded_and_capped(parcel):
    asset = svc.create_asset("Alice", {"template": "parcel", "name": "X"}, created_by="Alice")
    svc.update_asset("Alice", asset["id"], {"fields": {"county": "Bexar"}}, by="Alice")
    current = svc.get_asset("Alice", asset["id"])
    assert current["history"][-1]["action"] == "update"
    assert current["history"][-1]["changes"]["fields.county"] == [None, "Bexar"]
    for i in range(60):
        svc.update_asset("Alice", asset["id"], {"fields": {"acreage": i + 1}}, by="Alice")
    assert len(svc.get_asset("Alice", asset["id"])["history"]) == 50


# ---------------------------------------------------------------------------
# Sharing + hidden_from (request-based handshake)
# ---------------------------------------------------------------------------


def _accept(viewer, owner, asset_id, ws="personal"):
    svc.respond_to_asset_share(
        viewer, {"owner": owner, "workspace": ws, "asset_id": asset_id}, True
    )


def test_share_is_pending_until_accepted(parcel, users):
    sub, lot = _tree(users)
    svc.update_access(
        "Alice", sub["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    # Pending: Bob can't see it yet
    assert not any(a["id"] == sub["id"] for a in svc.list_visible("Bob", "personal"))
    assert svc.find_asset("Bob", "personal", sub["id"]) is None
    _accept("Bob", "Alice", sub["id"])
    visible = {a["id"]: a for a in svc.list_visible("Bob", "personal")}
    assert visible[sub["id"]]["_owner"] == "Alice"
    assert visible[lot["id"]]["_access"] == "read"
    found = svc.find_asset("Bob", "personal", lot["id"])
    assert found["relation"] == "shared" and found["can_edit"] is False


def test_share_request_notifies_recipient(parcel, users):
    from services import suggestions_service

    sub, _ = _tree(users)
    svc.update_access(
        "Alice", sub["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    notifs = suggestions_service.get_notifications("Bob")
    assert any(n.get("action", {}).get("type") == "asset_share" for n in notifs)


def test_decline_then_leave(parcel, users):
    sub, _ = _tree(users)
    svc.update_access(
        "Alice", sub["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    _accept("Bob", "Alice", sub["id"])
    assert any(a["id"] == sub["id"] for a in svc.list_visible("Bob", "personal"))
    svc.leave_asset_share("Bob", "Alice", sub["id"])
    assert not any(a["id"] == sub["id"] for a in svc.list_visible("Bob", "personal"))


def test_edit_share_can_edit(parcel, users):
    sub, lot = _tree(users)
    svc.update_access(
        "Alice", sub["id"], shared_with=[{"target": "Bob", "access": "edit"}], by="Alice"
    )
    _accept("Bob", "Alice", sub["id"])
    found = svc.find_asset("Bob", "personal", lot["id"])
    assert found["can_edit"] is True and found["can_manage"] is False


def test_household_share_personal_workspace(parcel, users):
    sub, _ = _tree(users)
    svc.update_access(
        "Alice",
        sub["id"],
        shared_with=[{"target": "household", "access": "read"}],
        by="Alice",
        asset_workspace="personal",
    )
    _accept("Bob", "Alice", sub["id"])
    assert any(a["id"] == sub["id"] for a in svc.list_visible("Bob", "personal"))


def test_legacy_share_without_accepted_is_open(parcel, users):
    # A pre-Phase-2 share entry (no `accepted` key) stays open to the target.
    sub, _ = _tree(users)
    store = svc._load("Alice", "personal")
    node = svc._by_id(store["assets"])[sub["id"]]
    node["shared_with"] = [{"target": "Bob", "access": "read"}]  # legacy shape
    svc._save("Alice", "personal", store)
    assets_index.reindex_owner("Alice", "personal")
    assert any(a["id"] == sub["id"] for a in svc.list_visible("Bob", "personal"))


def test_unknown_share_target_rejected(parcel, users):
    sub, _ = _tree(users)
    with pytest.raises(ValueError, match="Unknown share target"):
        svc.update_access(
            "Alice", sub["id"], shared_with=[{"target": "Charlie", "access": "read"}], by="Alice"
        )


def test_hidden_from_beats_share(parcel, users):
    sub, lot = _tree(users)
    svc.update_access(
        "Alice",
        sub["id"],
        shared_with=[{"target": "Bob", "access": "edit"}],
        hidden_from=["Bob"],
        by="Alice",
    )
    _accept("Bob", "Alice", sub["id"])  # even if Bob accepts, hidden_from wins
    assert not any(a["id"] in (sub["id"], lot["id"]) for a in svc.list_visible("Bob", "personal"))
    assert svc.find_asset("Bob", "personal", lot["id"]) is None


def test_share_this_node_only_no_cascade(parcel, users):
    sub, lot = _tree(users)
    svc.update_access(
        "Alice",
        sub["id"],
        shared_with=[{"target": "Bob", "access": "read"}],
        by="Alice",
        cascade=False,
    )
    _accept("Bob", "Alice", sub["id"])
    visible = {a["id"] for a in svc.list_visible("Bob", "personal")}
    assert sub["id"] in visible  # the node itself is shared
    assert lot["id"] not in visible  # child is NOT shared (per-node)
    assert svc.find_asset("Bob", "personal", lot["id"]) is None


def test_share_cascade_writes_descendants(parcel, users):
    sub, lot = _tree(users)
    svc.update_access(
        "Alice", sub["id"], shared_with=[{"target": "Bob", "access": "edit"}], by="Alice"
    )  # cascade defaults True
    assert svc.get_asset("Alice", lot["id"])["shared_with"][0]["target"] == "Bob"
    _accept("Bob", "Alice", sub["id"])  # accepting the root grants the subtree
    assert svc.find_asset("Bob", "personal", lot["id"])["can_edit"] is True


def test_orphan_by_sharing_visible_without_parent(parcel, users):
    sub, lot = _tree(users)
    # Share only the child; its parent stays private → child is an "orphan" the
    # recipient still sees (the frontend floats it to top level).
    svc.update_access(
        "Alice", lot["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    _accept("Bob", "Alice", lot["id"])
    visible = {a["id"] for a in svc.list_visible("Bob", "personal")}
    assert lot["id"] in visible and sub["id"] not in visible


def test_create_under_shared_inherits_audience(parcel, users):
    sub, _ = _tree(users)
    svc.update_access(
        "Alice", sub["id"], shared_with=[{"target": "Bob", "access": "edit"}], by="Alice"
    )
    _accept("Bob", "Alice", sub["id"])  # Bob is now in the accepted list
    child = svc.create_asset(
        "Alice",
        {"template": "parcel", "name": "New Lot", "parent_id": sub["id"]},
        created_by="Alice",
    )
    # Child inherits Bob-in-accepted → immediately visible/editable (group mechanic)
    assert child["shared_with"][0]["target"] == "Bob"
    assert "Bob" in child["shared_with"][0]["accepted"]
    assert svc.find_asset("Bob", "personal", child["id"])["can_edit"] is True


# ---------------------------------------------------------------------------
# Share index (derived routing cache)
# ---------------------------------------------------------------------------


def test_share_index_routes_only_sharers(parcel, users):
    sub, _ = _tree(users)
    # Before sharing, Bob has no sharers
    assert assets_index.sharers_for("Bob", "personal") == []
    svc.update_access(
        "Alice", sub["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    assert assets_index.sharers_for("Bob", "personal") == ["Alice"]
    # Removing the share clears the routing entry
    svc.update_access("Alice", sub["id"], shared_with=[], by="Alice")
    assert assets_index.sharers_for("Bob", "personal") == []


def test_share_index_group_target(parcel, users):
    sub, _ = _tree(users)
    svc.update_access(
        "Alice", sub["id"], shared_with=[{"target": "household", "access": "read"}], by="Alice"
    )
    assert "Alice" in assets_index.sharers_for("Bob", "personal")


def test_rebuild_share_index_parity(parcel, users):
    sub, _ = _tree(users)
    svc.update_access(
        "Alice", sub["id"], shared_with=[{"target": "Bob", "access": "edit"}], by="Alice"
    )
    before = assets_index.sharers_for("Bob", "personal")
    assets_index.rebuild_share_index()  # full rescan must match incremental state
    assert assets_index.sharers_for("Bob", "personal") == before == ["Alice"]


def test_delete_clears_share_index(parcel, users):
    sub, _ = _tree(users)
    # a standalone shared asset (no children) so delete is allowed
    lone = svc.create_asset("Alice", {"template": "parcel", "name": "Lone"}, created_by="Alice")
    svc.update_access(
        "Alice", lone["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    assert assets_index.sharers_for("Bob", "personal") == ["Alice"]
    svc.delete_asset("Alice", lone["id"])
    assert assets_index.sharers_for("Bob", "personal") == []


# ---------------------------------------------------------------------------
# Pool ownership
# ---------------------------------------------------------------------------


def test_convert_moves_subtree_strips_shares_and_moves_files(parcel, users):
    sub, lot = _tree(users)
    svc.update_access(
        "Alice", sub["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    svc.add_attachment("Alice", lot["id"], "plat.pdf", "application/pdf", b"%PDF", by="Alice")

    root = svc.convert_to_pool("Alice", sub["id"], workspace="personal", by="Alice")
    assert root["parent_id"] is None
    assert root["shared_with"] == []
    assert svc.list_assets("Alice", "personal") == []
    pool_ids = {a["id"] for a in svc.list_assets("_household")}
    assert {sub["id"], lot["id"]} <= pool_ids
    assert (assets_files_path("_household") / lot["id"]).exists()
    assert not (assets_files_path("Alice") / lot["id"]).exists()


def test_pool_assets_visible_to_all_members_and_gated(parcel, users):
    sub, _ = _tree(users)
    svc.convert_to_pool("Alice", sub["id"], by="Alice")
    visible = {a["id"]: a for a in svc.list_visible("Bob", "personal")}
    assert visible[sub["id"]]["_owner"] == "household"
    assert visible[sub["id"]]["_access"] == "read"
    found = svc.find_asset("Bob", "personal", sub["id"])
    assert found["relation"] == "pool" and found["can_edit"] is False
    granted = svc.find_asset("Bob", "personal", sub["id"], pool_edit=["household"])
    assert granted["can_edit"] is True and granted["can_delete"] is False


def test_pool_hidden_from_respected_except_admin(parcel, users):
    sub, _ = _tree(users)
    svc.convert_to_pool("Alice", sub["id"], by="Alice")
    svc.update_access("_household", sub["id"], hidden_from=["Bob"], by="Alice")
    assert not any(a["id"] == sub["id"] for a in svc.list_visible("Bob", "personal"))
    assert svc.find_asset("Bob", "personal", sub["id"]) is None
    assert any(a["id"] == sub["id"] for a in svc.list_visible("Alice", "personal", is_admin=True))


def test_pool_assets_survive_owner_deletion(parcel, users):
    sub, lot = _tree(users)
    svc.convert_to_pool("Alice", sub["id"], by="Alice")
    shutil.rmtree(user_path("Alice"))  # what admin user-deletion does to the Brain folder
    pool_ids = {a["id"] for a in svc.list_assets("_household")}
    assert {sub["id"], lot["id"]} <= pool_ids
    assert any(a["id"] == lot["id"] for a in svc.list_visible("Bob", "personal"))


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


def test_attachment_roundtrip_and_disk_name(parcel):
    asset = svc.create_asset("Alice", {"template": "parcel", "name": "X"}, created_by="Alice")
    att = svc.add_attachment(
        "Alice", asset["id"], "../../evil name.pdf", "application/pdf", b"%PDF", by="Alice"
    )
    assert att["filename"] == "evil name.pdf"
    disk = assets_files_path("Alice") / asset["id"] / f"{att['id']}.pdf"
    assert disk.exists()
    meta = svc.get_attachment("Alice", asset["id"], att["id"])
    assert meta["mime"] == "application/pdf"
    assert svc.delete_attachment("Alice", asset["id"], att["id"], by="Alice") is True
    assert not disk.exists()
    assert svc.get_asset("Alice", asset["id"])["attachments"] == []


def test_attachment_type_size_and_count_limits(parcel):
    asset = svc.create_asset("Alice", {"template": "parcel", "name": "X"}, created_by="Alice")
    with pytest.raises(ValueError, match="Unsupported file type"):
        svc.add_attachment("Alice", asset["id"], "x.exe", "application/x-dosexec", b"x", by="Alice")
    with pytest.raises(ValueError, match="too large"):
        svc.add_attachment(
            "Alice",
            asset["id"],
            "big.pdf",
            "application/pdf",
            b"x" * (svc.MAX_ATTACHMENT_BYTES + 1),
            by="Alice",
        )
    for i in range(svc.MAX_ATTACHMENTS):
        svc.add_attachment("Alice", asset["id"], f"f{i}.pdf", "application/pdf", b"%", by="Alice")
    with pytest.raises(ValueError, match="limit"):
        svc.add_attachment("Alice", asset["id"], "over.pdf", "application/pdf", b"%", by="Alice")


# ---------------------------------------------------------------------------
# Automation token + task linking
# ---------------------------------------------------------------------------


def test_automation_token_generated_once_and_rotates(brain):
    first = automations_config.get_api_token()
    assert first == automations_config.get_api_token()
    assert automations_config.verify_api_token(first)
    rotated = automations_config.rotate_api_token()
    assert rotated != first
    assert not automations_config.verify_api_token(first)


def test_task_asset_id_passthrough(users):
    task = task_service.add_task("Alice", {"title": "Survey lot", "asset_id": "abc123"})
    assert task["asset_id"] == "abc123"
    updated = task_service.update_task("Alice", task["id"], {"asset_id": None})
    assert updated["asset_id"] is None
