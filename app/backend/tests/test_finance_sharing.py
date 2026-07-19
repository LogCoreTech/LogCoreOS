"""Finance Phase E: shares + handshake, pool contributors, specificity ladder,
contribute caps (server-side enforcement), hidden_from, share index."""

import pytest

from services import finance_index
from services import finance_service as fin


@pytest.fixture(autouse=True)
def users(brain, monkeypatch):
    from services import auth_service

    roster = [
        {"name": "Owner", "role": "admin", "workspaces": ["personal", "business"]},
        {
            "name": "Worker",
            "role": "member",
            "workspaces": ["personal", "business"],
            "feature_role": "crew",
        },
        {"name": "Spouse", "role": "member", "workspaces": ["personal"]},
    ]
    monkeypatch.setattr(auth_service, "list_users", lambda: roster)
    return roster


@pytest.fixture()
def book(brain):
    return fin.create_book("Owner", "personal", name="Family budget", created_by="Owner")


@pytest.fixture()
def checking(brain, book):
    return fin.add_account(
        "Owner",
        "personal",
        book["id"],
        {"name": "Checking", "type": "checking", "opening_balance_cents": 100_00},
    )


def _access(viewer, book_id, role="member", admin=False, ws="personal", account_id=None):
    found = fin.find_book(viewer, role, admin, ws, book_id)
    if not found:
        return (None, None)
    store, fresh, _acc = found
    return fin._resolve_book_access(viewer, role, admin, store, fresh, account_id, ws)


def _share(book_id, entries, hidden=None, account_id=None):
    return fin.update_access(
        "Owner",
        "personal",
        book_id,
        shared_with=entries,
        hidden_from=hidden,
        account_id=account_id,
    )


# ---------------------------------------------------------------------------
# Handshake + visibility
# ---------------------------------------------------------------------------


def test_share_hidden_until_accepted_then_visible(brain, book, checking):
    _record, to_notify = _share(book["id"], [{"target": "Worker", "access": "read"}])
    assert to_notify == ["Worker"]
    # Not accepted yet → invisible
    assert fin.find_book("Worker", "member", False, "personal", book["id"]) is None
    # Accept → visible read
    assert fin.respond_share("Worker", "Owner", "personal", book["id"], accept=True)
    found = fin.find_book("Worker", "member", False, "personal", book["id"])
    assert found is not None and found[2] == "read"
    listed = fin.list_visible_books("Worker", "member", False, "personal")
    entry = next(b for b in listed if b["id"] == book["id"])
    assert entry["_owner"] == "Owner" and entry["_access"] == "read"


def test_decline_removes_by_name_entry(brain, book, checking):
    _share(book["id"], [{"target": "Worker", "access": "edit"}])
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=False)
    fresh = fin.get_book("Owner", "personal", book["id"])
    assert fresh["shared_with"] == []  # owner no longer lists them
    assert fin.find_book("Worker", "member", False, "personal", book["id"]) is None


def test_leave_after_accept_drops_group_membership(brain, book, checking):
    _share(book["id"], [{"target": "household", "access": "read"}])
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=True)
    assert fin.find_book("Worker", "member", False, "personal", book["id"]) is not None
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=False)
    assert fin.find_book("Worker", "member", False, "personal", book["id"]) is None
    # Group entry itself survives for other members
    fresh = fin.get_book("Owner", "personal", book["id"])
    assert fresh["shared_with"][0]["target"] == "household"


def test_reshare_preserves_acceptance(brain, book, checking):
    _share(book["id"], [{"target": "Worker", "access": "read"}])
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=True)
    # Owner re-writes the audience (e.g. changing access level)
    _record, to_notify = _share(book["id"], [{"target": "Worker", "access": "edit"}])
    assert to_notify == []  # already accepted — no new request
    assert _access("Worker", book["id"])[0] == "edit"


def test_hidden_from_beats_shares_and_roles(brain, book, checking):
    _share(book["id"], [{"target": "household", "access": "read"}], hidden=["Spouse"])
    fin.respond_share("Spouse", "Owner", "personal", book["id"], accept=True)
    assert fin.find_book("Spouse", "member", False, "personal", book["id"]) is None
    # role: hide keeps future crew out
    with pytest.raises(ValueError):
        _share(book["id"], None, hidden=["role:doesnotexist"])


# ---------------------------------------------------------------------------
# Specificity ladder + caps
# ---------------------------------------------------------------------------


def test_by_name_entry_overrides_group(brain, book, checking):
    _share(
        book["id"],
        [
            {"target": "household", "access": "edit"},
            {"target": "Worker", "access": "contribute", "caps": {"add": ["expense"]}},
        ],
    )
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=True)
    fin.respond_share("Spouse", "Owner", "personal", book["id"], accept=True)
    # Group member gets edit; the individually-restricted member gets contribute
    assert _access("Spouse", book["id"])[0] == "edit"
    access, caps = _access("Worker", book["id"])
    assert access == "contribute"
    assert caps["add"] == ["expense"] and caps["see_balances"] is False


def test_account_override_beats_book_share(brain, book, checking):
    savings = fin.add_account(
        "Owner", "personal", book["id"], {"name": "Savings", "type": "savings"}
    )
    _share(book["id"], [{"target": "Worker", "access": "edit"}])
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=True)
    # Account-level by-name read override kills edit on that account only
    fin.update_access(
        "Owner",
        "personal",
        book["id"],
        shared_with=[{"target": "Worker", "access": "read"}],
        account_id=savings["id"],
    )
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=True)
    assert _access("Worker", book["id"], account_id=savings["id"])[0] == "read"
    assert _access("Worker", book["id"], account_id=checking["id"])[0] == "edit"


def test_caps_union_across_same_rung(brain, book, checking):
    from services.features_service import load_features, save_features

    features = load_features()
    features["roles"]["crew"] = {m: True for m in ("dashboard", "finance")}
    save_features(features)
    _share(
        book["id"],
        [
            {"target": "household", "access": "contribute", "caps": {"add": ["expense"]}},
            {
                "target": "role:crew",
                "access": "contribute",
                "caps": {"add": ["income"], "see_balances": True},
            },
        ],
    )
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=True)
    access, caps = _access("Worker", book["id"], role="crew")
    assert access == "contribute"
    assert caps["add"] == ["expense", "income"]  # union
    assert caps["see_balances"] is True


# ---------------------------------------------------------------------------
# Pool contributors (no handshake)
# ---------------------------------------------------------------------------


def test_pool_contributors_no_handshake_and_admin_never_restricted(brain):
    pool_book = fin.create_book("_household", "personal", name="House", created_by="Owner")
    fin.add_account(
        "_household", "personal", pool_book["id"], {"name": "Joint", "type": "checking"}
    )
    fin.update_access(
        "_household",
        "personal",
        pool_book["id"],
        contributors=[
            {
                "target": "Worker",
                "access": "contribute",
                "caps": {"add": ["expense"], "see_balances": True},
            }
        ],
    )
    # No accept step needed — caps apply immediately
    access, caps = _access("Worker", pool_book["id"])
    assert access == "contribute" and caps["see_balances"] is True
    # Other members keep plain read; admins keep edit
    assert _access("Spouse", pool_book["id"])[0] == "read"
    assert _access("Owner", pool_book["id"], admin=True)[0] == "edit"
    # shared_with is rejected on pool books
    with pytest.raises(ValueError):
        fin.update_access(
            "_household",
            "personal",
            pool_book["id"],
            shared_with=[{"target": "Worker", "access": "read"}],
        )


def test_pool_hidden_from_role(brain):
    pool_book = fin.create_book("_household", "personal", name="House", created_by="Owner")
    from services.features_service import load_features, save_features

    features = load_features()
    features["roles"]["crew"] = {m: True for m in ("dashboard", "finance")}
    save_features(features)
    fin.update_access("_household", "personal", pool_book["id"], hidden_from=["role:crew"])
    assert _access("Worker", pool_book["id"], role="crew")[0] is None
    assert _access("Spouse", pool_book["id"])[0] == "read"


# ---------------------------------------------------------------------------
# Share index routing
# ---------------------------------------------------------------------------


def test_share_index_routes_sharers(brain, book, checking):
    assert finance_index.sharers_for("Worker", "member", "personal") == []
    _share(book["id"], [{"target": "Worker", "access": "read"}])
    assert finance_index.sharers_for("Worker", "member", "personal") == ["Owner"]
    assert finance_index.sharers_for("Spouse", "member", "personal") == []
    # Rebuild from scratch matches incremental state
    finance_index.rebuild_share_index()
    assert finance_index.sharers_for("Worker", "member", "personal") == ["Owner"]
    # Decline removes the entry and the index route
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=False)
    assert finance_index.sharers_for("Worker", "member", "personal") == []


# ---------------------------------------------------------------------------
# Server-side caps enforcement (service-level output, not UI)
# ---------------------------------------------------------------------------


def test_default_caps_are_expense_submission(brain):
    caps = fin.normalize_caps(None)
    assert caps == {
        "add": ["expense"],
        "edit_own": True,
        "see_balances": False,
        "see_all_tx": False,
    }


def test_net_worth_skips_capped_books(brain, book, checking):
    from services import finance_reports

    _share(book["id"], [{"target": "Worker", "access": "contribute"}])
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=True)
    result = finance_reports.net_worth("Worker", "member", False, "personal")
    assert result["books"] == [] and result["total_cents"] == 0
    # With see_balances the book counts
    _share(
        book["id"], [{"target": "Worker", "access": "contribute", "caps": {"see_balances": True}}]
    )
    result = finance_reports.net_worth("Worker", "member", False, "personal")
    assert result["total_cents"] == 100_00


def test_contribute_created_by_filter(brain, book, checking):
    _share(book["id"], [{"target": "Worker", "access": "contribute"}])
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=True)
    fin.add_transaction(
        "Owner",
        "personal",
        book,
        {
            "date": "2026-07-01",
            "amount_cents": -50_00,
            "account_id": checking["id"],
            "category": "",
        },
        "Owner",
    )
    fin.add_transaction(
        "Owner",
        "personal",
        book,
        {
            "date": "2026-07-02",
            "amount_cents": -10_00,
            "account_id": checking["id"],
            "category": "",
        },
        "Worker",
    )
    own_only, total = fin.list_transactions("Owner", "personal", book["id"], created_by="Worker")
    assert total == 1 and own_only[0]["created_by"] == "Worker"


def test_asset_transactions_contribute_sees_own_entries_only(brain, book, checking):
    """list_transactions_for_asset applies the same caps rule as the tx list:
    a contribute viewer without see_all_tx gets only their own entries."""
    _share(book["id"], [{"target": "Worker", "access": "contribute", "caps": {"add": ["expense"]}}])
    fin.respond_share("Worker", "Owner", "personal", book["id"], accept=True)
    fin.add_transaction(
        "Owner",
        "personal",
        book["id"],
        {
            "date": "2026-07-01",
            "amount_cents": -20_00,
            "account_id": checking["id"],
            "category": "",
            "asset_id": "asset-1",
        },
        created_by="Owner",
    )
    fin.add_transaction(
        "Owner",
        "personal",
        book["id"],
        {
            "date": "2026-07-02",
            "amount_cents": -10_00,
            "account_id": checking["id"],
            "category": "",
            "asset_id": "asset-1",
        },
        created_by="Worker",
    )
    seen = fin.list_transactions_for_asset("Worker", "crew", False, "personal", "asset-1")
    assert [t["created_by"] for t in seen] == ["Worker"]
    # The owner still sees both
    assert (
        len(fin.list_transactions_for_asset("Owner", "member", False, "personal", "asset-1")) == 2
    )
