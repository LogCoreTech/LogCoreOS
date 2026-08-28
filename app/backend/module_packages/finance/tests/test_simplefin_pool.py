"""Pool-owned SimpleFIN connections — a joint/family bank account connected
directly to the _household/_team pseudo-user, independent of any one
member's own connection. Router functions are imported and called directly
(mirroring test_features.py) since the pool-name validation and delegation
logic lives in routers/finance_banking.py, not in simplefin_service.py
itself — which is already generic on user_name and needs no pool-specific
code at all.
"""

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException

from module_packages.finance.backend.router_banking import (
    MappingEntry,
    MappingRequest,
    MappingTarget,
    PoolClaimRequest,
    pool_bank_accounts,
    pool_claim,
    pool_disconnect,
    pool_reveal,
    pool_set_mapping,
    pool_status,
    pool_sync_now,
)
from services import auth_service
from services import finance_service as fin
from services import simplefin_service as sf


@pytest.fixture()
def admin(brain):
    return auth_service.create_user("admin@example.com", "password123", "Admin", role="admin")


class _FakeResponse:
    def __init__(self, text=""):
        self.text = text

    def raise_for_status(self):
        pass


def test_pool_status_rejects_unknown_pool(admin):
    with pytest.raises(HTTPException) as exc:
        pool_status("garage", admin)
    assert exc.value.status_code == 400


def test_pool_status_not_connected_by_default(admin):
    assert pool_status("household", admin)["connected"] is False


def test_pool_claim_and_reveal(admin, monkeypatch):
    url = "https://bridge.simplefin.org/claim/joint-account"
    token = base64.b64encode(url.encode()).decode()
    monkeypatch.setattr(
        sf.httpx, "post", lambda u, timeout: _FakeResponse(text="https://u:p@bridge/joint")
    )

    status = pool_claim("household", PoolClaimRequest(setup_token=token), admin)
    assert status["connected"] is True
    assert "access_url" not in status  # status never leaks the URL

    revealed = pool_reveal("household", admin)
    assert revealed["access_url"] == "https://u:p@bridge/joint"

    # A completely separate connection from a real user's own
    assert sf.get_connection("_household")["access_url"] == "https://u:p@bridge/joint"


def test_pool_reveal_404_when_not_connected(admin):
    with pytest.raises(HTTPException) as exc:
        pool_reveal("team", admin)
    assert exc.value.status_code == 404


def test_pool_disconnect_and_sync_404_when_not_connected(admin):
    with pytest.raises(HTTPException):
        pool_disconnect("household", admin)
    with pytest.raises(HTTPException):
        pool_sync_now("household", admin)


def test_pool_accounts_requires_connection(admin):
    with pytest.raises(HTTPException) as exc:
        pool_bank_accounts("household", admin)
    assert exc.value.status_code == 400


def test_pool_mapping_targets_the_same_pools_own_books(admin):
    sf.save_connection(
        "_household",
        {
            "access_url": "https://u:p@bridge/joint",
            "claimed_at": "2026-08-12T00:00:00+00:00",
            "last_sync": None,
            "last_error": None,
            "error_notified_at": None,
            "account_map": [],
        },
    )
    pool_book = fin.create_book("_household", "personal", name="House", created_by="Admin")
    pool_acct = fin.add_account(
        "_household", "personal", pool_book["id"], {"name": "Joint", "type": "checking"}
    )

    req = MappingRequest(
        entries=[
            MappingEntry(
                simplefin_account_id="ACT-1",
                bank_name="Chase",
                account_name="Joint Checking",
                target=MappingTarget(
                    store="household",
                    workspace="personal",
                    book_id=pool_book["id"],
                    account_id=pool_acct["id"],
                ),
            )
        ]
    )
    status = pool_set_mapping("household", req, admin)
    entry = status["account_map"][0]
    assert entry["target"]["book_id"] == pool_book["id"]
    # The connection itself lives at the pool's own pseudo-user, not any real user
    assert sf.get_connection("Admin") is None
    assert sf.get_connection("_household")["account_map"][0]["simplefin_account_id"] == "ACT-1"


def test_sync_all_users_includes_connected_pools(admin, monkeypatch):
    sf.save_connection(
        "_household",
        {
            "access_url": "https://u:p@bridge/joint",
            "claimed_at": "2026-08-12T00:00:00+00:00",
            "last_sync": None,
            "last_error": None,
            "error_notified_at": None,
            "account_map": [],
        },
    )
    pool_book = fin.create_book("_household", "personal", name="House", created_by="Admin")
    pool_acct = fin.add_account(
        "_household", "personal", pool_book["id"], {"name": "Joint", "type": "checking"}
    )
    sf.set_mapping(
        "_household",
        [
            {
                "simplefin_account_id": "ACT-1",
                "target": {
                    "store": "household",
                    "workspace": "personal",
                    "book_id": pool_book["id"],
                    "account_id": pool_acct["id"],
                },
            }
        ],
        is_admin=True,
    )

    def fake_fetch(user, start_ts=None):
        assert user == "_household"
        return [
            {
                "id": "ACT-1",
                "name": "Joint",
                "currency": "USD",
                "balance": "500.00",
                "org": {"name": "Chase"},
                "transactions": [
                    {
                        "id": "TX-1",
                        "posted": 1755000000,
                        "amount": "-20.00",
                        "description": "Groceries",
                    }
                ],
            }
        ]

    monkeypatch.setattr(sf, "fetch_accounts", fake_fetch)

    totals = sf.sync_all_users()
    assert totals["users"] == 1
    assert totals["created"] == 1
    items, total = fin.list_transactions("_household", "personal", pool_book["id"])
    assert total == 1
    assert items[0]["simplefin_id"] == "TX-1"
