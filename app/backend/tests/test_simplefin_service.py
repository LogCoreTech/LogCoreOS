"""Finance Phase B: SimpleFIN claim/mapping/sync + payee rules + CSV import."""

import base64

import pytest

from services import finance_import_service as csv_svc
from services import finance_service as fin
from services import simplefin_service as sf


@pytest.fixture()
def book(brain):
    return fin.create_book("Alice", "personal", name="Family budget", created_by="Alice")


@pytest.fixture()
def checking(brain, book):
    return fin.add_account(
        "Alice", "personal", book["id"], {"name": "Checking", "type": "checking"}
    )


class _FakeResponse:
    def __init__(self, text="", json_data=None, status=200):
        self.text = text
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise sf.httpx.HTTPStatusError("boom", request=None, response=None)

    def json(self):
        return self._json


def _connect(user="Alice"):
    sf.save_connection(
        user,
        {
            "access_url": "https://u:p@bridge.example/simplefin",
            "claimed_at": "2026-07-12T00:00:00+00:00",
            "last_sync": None,
            "last_error": None,
            "error_notified_at": None,
            "account_map": [],
        },
    )


def _bank_payload(txs, balance="150.00"):
    return [
        {
            "id": "ACT-1",
            "name": "Chase Checking",
            "currency": "USD",
            "balance": balance,
            "org": {"name": "Chase"},
            "transactions": txs,
        }
    ]


def _map_to(book, checking, user="Alice", is_admin=False, store="self"):
    return sf.set_mapping(
        user,
        [
            {
                "simplefin_account_id": "ACT-1",
                "bank_name": "Chase",
                "account_name": "Checking",
                "target": {
                    "store": store,
                    "workspace": "personal",
                    "book_id": book["id"],
                    "account_id": checking["id"],
                },
                "enabled": True,
            }
        ],
        is_admin=is_admin,
    )


# ---------------------------------------------------------------------------
# Claim + parsing
# ---------------------------------------------------------------------------


def test_decode_setup_token():
    url = "https://bridge.simplefin.org/claim/abc123"
    token = base64.b64encode(url.encode()).decode()
    assert sf.decode_setup_token(token) == url
    with pytest.raises(ValueError):
        sf.decode_setup_token("not-base64!!!")
    with pytest.raises(ValueError):
        sf.decode_setup_token(base64.b64encode(b"http://insecure/claim").decode())


def test_claim_and_save(brain, monkeypatch):
    url = "https://bridge.simplefin.org/claim/abc123"
    token = base64.b64encode(url.encode()).decode()
    monkeypatch.setattr(
        sf.httpx, "post", lambda u, timeout: _FakeResponse(text="https://u:p@bridge/simplefin")
    )
    status = sf.claim_and_save("Alice", token)
    assert status["connected"] is True
    conn = sf.get_connection("Alice")
    assert conn["access_url"] == "https://u:p@bridge/simplefin"
    # Status never leaks the access URL
    assert "access_url" not in status


def test_amount_to_cents():
    assert sf.amount_to_cents("-45.99") == -4599
    assert sf.amount_to_cents("0.10") == 10
    assert sf.amount_to_cents("2500") == 250000
    assert sf.amount_to_cents(None) is None
    assert sf.amount_to_cents("abc") is None


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def test_mapping_validates_and_pool_requires_admin(brain, book, checking):
    _connect()
    status = _map_to(book, checking)
    assert status["account_map"][0]["target"]["book_id"] == book["id"]

    # Unknown book
    with pytest.raises(ValueError):
        sf.set_mapping(
            "Alice",
            [
                {
                    "simplefin_account_id": "ACT-1",
                    "target": {
                        "store": "self",
                        "workspace": "personal",
                        "book_id": "00000000-0000-0000-0000-000000000000",
                        "account_id": checking["id"],
                    },
                }
            ],
            is_admin=False,
        )

    # Pool target requires admin
    pool_book = fin.create_book("_household", "personal", name="House", created_by="Admin")
    pool_acct = fin.add_account(
        "_household", "personal", pool_book["id"], {"name": "Joint", "type": "checking"}
    )
    entry = {
        "simplefin_account_id": "ACT-1",
        "target": {
            "store": "household",
            "workspace": "personal",
            "book_id": pool_book["id"],
            "account_id": pool_acct["id"],
        },
    }
    with pytest.raises(PermissionError):
        sf.set_mapping("Alice", [entry], is_admin=False)
    status = sf.set_mapping("Alice", [entry], is_admin=True)
    assert status["account_map"][0]["target"]["store"] == "household"


# ---------------------------------------------------------------------------
# Sync engine
# ---------------------------------------------------------------------------


def test_sync_creates_then_dedups(brain, book, checking, monkeypatch):
    _connect()
    _map_to(book, checking)
    txs = [
        {"id": "TX-1", "posted": 1752300000, "amount": "-45.99", "description": "KROGER #123"},
        {"id": "TX-2", "posted": 1752300100, "amount": "2500.00", "payee": "ACME PAYROLL"},
    ]
    monkeypatch.setattr(sf, "fetch_accounts", lambda user, start_ts=None: _bank_payload(txs))

    result = sf.sync_user("Alice", notify_on_error=False)
    assert result["created"] == 2

    items, total = fin.list_transactions("Alice", "personal", book["id"])
    assert total == 2
    assert {t["source"] for t in items} == {"simplefin"}
    assert {t["simplefin_id"] for t in items} == {"TX-1", "TX-2"}
    assert all(t["category"] == "" for t in items)  # lands uncategorized

    # Bank balance recorded as source data on the account
    fresh = fin.get_book("Alice", "personal", book["id"])
    acct = fresh["accounts"][0]
    assert acct["synced_balance_cents"] == 15000
    assert acct["simplefin_account_id"] == "ACT-1"

    # Re-sync twice with the same (overlapping) feed → zero duplicates
    for _ in range(2):
        result = sf.sync_user("Alice", notify_on_error=False)
        assert result["created"] == 0
    _items, total = fin.list_transactions("Alice", "personal", book["id"])
    assert total == 2


def test_sync_applies_learned_rules(brain, book, checking, monkeypatch):
    _connect()
    _map_to(book, checking)
    fin.learn_rule("Alice", "personal", book["id"], "KROGER #123", "Groceries")

    txs = [{"id": "TX-9", "posted": 1752300000, "amount": "-12.00", "description": "kroger  #123"}]
    monkeypatch.setattr(sf, "fetch_accounts", lambda user, start_ts=None: _bank_payload(txs))
    sf.sync_user("Alice", notify_on_error=False)

    items, _ = fin.list_transactions("Alice", "personal", book["id"])
    assert items[0]["category"] == "Groceries"


def test_rule_not_applied_when_category_removed(brain, book, checking):
    fin.learn_rule("Alice", "personal", book["id"], "Netflix", "Dining")
    fresh = fin.get_book("Alice", "personal", book["id"])
    new_cats = [c for c in fresh["categories"] if c["name"] != "Dining"]
    fin.update_book("Alice", "personal", book["id"], {"categories": new_cats})
    fresh = fin.get_book("Alice", "personal", book["id"])
    assert fin.apply_rules("Alice", "personal", fresh, "NETFLIX") == ""


def test_sync_error_notifies_once_per_day(brain, book, checking, monkeypatch):
    _connect()
    _map_to(book, checking)

    def boom(user, start_ts=None):
        raise ValueError("bridge unreachable")

    monkeypatch.setattr(sf, "fetch_accounts", boom)

    sent = []
    from services import auth_service, suggestions_service

    monkeypatch.setattr(auth_service, "list_users", lambda: [{"name": "Boss", "role": "admin"}])
    monkeypatch.setattr(
        suggestions_service,
        "notify_user",
        lambda name, title, body, **kw: sent.append(name),
    )

    sf.sync_user("Alice")
    assert sorted(set(sent)) == ["Alice", "Boss"]
    count_after_first = len(sent)
    sf.sync_user("Alice")  # same day → throttled, no new notifications
    assert len(sent) == count_after_first
    assert sf.get_connection("Alice")["last_error"]


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

CSV_CONTENT = b"""Date,Description,Amount
2026-07-01,KROGER #123,-45.99
2026-07-02,ACME PAYROLL,"2,500.00"
2026-07-03,COFFEE SHOP,(4.50)
"""


def test_csv_preview():
    preview = csv_svc.preview_csv(CSV_CONTENT)
    assert preview["headers"] == ["Date", "Description", "Amount"]
    assert preview["total_rows"] == 3
    assert len(preview["rows"]) == 3


def test_csv_amount_and_date_parsing():
    assert csv_svc.parse_amount("-45.99") == -4599
    assert csv_svc.parse_amount("(4.50)") == -450
    assert csv_svc.parse_amount("$2,500.00") == 250000
    assert csv_svc.parse_date("07/03/2026") == "2026-07-03"
    assert csv_svc.parse_date("2026-07-03") == "2026-07-03"
    with pytest.raises(ValueError):
        csv_svc.parse_date("yesterday")


def test_csv_commit_and_reimport_skips(brain, book, checking):
    fresh = fin.get_book("Alice", "personal", book["id"])
    mapping = {
        "account_id": checking["id"],
        "date_col": "Date",
        "amount_col": "Amount",
        "payee_col": "Description",
    }
    result = csv_svc.commit_csv("Alice", "personal", fresh, CSV_CONTENT, mapping, "Alice")
    assert result["created"] == 3
    items, total = fin.list_transactions("Alice", "personal", book["id"])
    assert total == 3
    assert {t["source"] for t in items} == {"csv"}
    paren = next(t for t in items if t["payee"] == "COFFEE SHOP")
    assert paren["amount_cents"] == -450

    # Re-import the exact same file → everything skipped by import_hash
    result = csv_svc.commit_csv("Alice", "personal", fresh, CSV_CONTENT, mapping, "Alice")
    assert result["created"] == 0
    assert result["skipped"] == 3


def test_csv_invert_amounts(brain, book, checking):
    fresh = fin.get_book("Alice", "personal", book["id"])
    content = b"Date,Amount\n2026-07-05,45.99\n"
    mapping = {
        "account_id": checking["id"],
        "date_col": "Date",
        "amount_col": "Amount",
        "invert_amounts": True,
    }
    csv_svc.commit_csv("Alice", "personal", fresh, content, mapping, "Alice")
    items, _ = fin.list_transactions("Alice", "personal", book["id"])
    assert items[0]["amount_cents"] == -4599


def test_csv_bad_rows_reported_not_fatal(brain, book, checking):
    fresh = fin.get_book("Alice", "personal", book["id"])
    content = b"Date,Amount\n2026-07-05,45.99\nnot-a-date,1.00\n2026-07-06,oops\n"
    mapping = {"account_id": checking["id"], "date_col": "Date", "amount_col": "Amount"}
    result = csv_svc.commit_csv("Alice", "personal", fresh, content, mapping, "Alice")
    assert result["created"] == 1
    assert len(result["errors"]) == 2
