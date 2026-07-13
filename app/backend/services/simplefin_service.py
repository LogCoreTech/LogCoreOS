"""SimpleFIN Bridge integration — read-only bank data, admin-managed.

Security model:
- The user NEVER enters bank credentials anywhere. They connect their banks at
  SimpleFIN's side and hand over a one-time SETUP TOKEN; claiming it yields a
  read-only ACCESS URL. By protocol that URL can only read balances and
  transactions — it cannot move money.
- Connections are ADMIN-MANAGED: members request one (admins get notified),
  an admin claims the token. The access URL is stored per user at
  brain/USERS/{name}/Finance/simplefin.json — never logged, never in git,
  returned only by the admin-gated, rate-limited reveal endpoint.
- Members map connected bank accounts onto accounts in their own books;
  mapping a bank account onto a POOL book (household/team) is admin-only.
"""

import base64
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

import httpx

from services import finance_service
from services.file_service import read_json, simplefin_path, write_json

logger = logging.getLogger("logcore.simplefin")

_TIMEOUT = 25.0
_OVERLAP_DAYS = 7  # re-fetch window so late-posting transactions are never missed
_FIRST_SYNC_DAYS = 90
_ERROR_NOTIFY_EVERY = timedelta(hours=24)

VALID_TARGET_STORES = {"self", "household", "team"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Connection storage
# ---------------------------------------------------------------------------


def get_connection(user_name: str) -> dict | None:
    path = simplefin_path(user_name)
    if not path.exists():
        return None
    data = read_json(path, default={})
    return data if data.get("access_url") else None


def save_connection(user_name: str, data: dict) -> None:
    write_json(simplefin_path(user_name), data)


def disconnect(user_name: str) -> bool:
    path = simplefin_path(user_name)
    if not path.exists():
        return False
    path.unlink()
    return True


def connection_status(user_name: str) -> dict:
    """Sanitized status — NEVER includes the access URL."""
    conn = get_connection(user_name)
    if not conn:
        return {"connected": False}
    return {
        "connected": True,
        "claimed_at": conn.get("claimed_at"),
        "last_sync": conn.get("last_sync"),
        "last_error": conn.get("last_error"),
        "account_map": conn.get("account_map", []),
    }


# ---------------------------------------------------------------------------
# Claim flow (setup token → access URL)
# ---------------------------------------------------------------------------


def decode_setup_token(setup_token: str) -> str:
    """A SimpleFIN setup token is the base64-encoded claim URL."""
    try:
        claim_url = base64.b64decode(setup_token.strip(), validate=True).decode("utf-8").strip()
    except Exception:
        raise ValueError("That doesn't look like a SimpleFIN setup token.")
    if not claim_url.startswith("https://"):
        raise ValueError("Setup token must decode to an https claim URL.")
    return claim_url


def claim_and_save(user_name: str, setup_token: str) -> dict:
    """Claim the setup token (one-time POST) and store the access URL."""
    claim_url = decode_setup_token(setup_token)
    try:
        resp = httpx.post(claim_url, timeout=_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ValueError(f"SimpleFIN claim failed: {exc}")
    access_url = resp.text.strip()
    if not access_url.startswith("http"):
        raise ValueError("SimpleFIN did not return a valid access URL.")
    conn = {
        "access_url": access_url,
        "claimed_at": _now().isoformat(),
        "last_sync": None,
        "last_error": None,
        "error_notified_at": None,
        "account_map": (
            get_connection(user_name).get("account_map", []) if get_connection(user_name) else []
        ),
    }
    save_connection(user_name, conn)
    return connection_status(user_name)


# ---------------------------------------------------------------------------
# Fetching (read-only)
# ---------------------------------------------------------------------------


def _split_auth(access_url: str) -> tuple[str, tuple[str, str] | None]:
    """Extract userinfo credentials from the access URL into an httpx auth pair."""
    parts = urlsplit(access_url)
    if parts.username is None:
        return access_url, None
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    bare = urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    return bare, (parts.username or "", parts.password or "")


def fetch_accounts(user_name: str, start_ts: int | None = None) -> list[dict]:
    """GET /accounts from the bridge. Raises ValueError on any failure."""
    conn = get_connection(user_name)
    if not conn:
        raise ValueError("No SimpleFIN connection")
    url, auth = _split_auth(conn["access_url"])
    params = {}
    if start_ts is not None:
        params["start-date"] = str(int(start_ts))
    try:
        resp = httpx.get(f"{url}/accounts", params=params, auth=auth, timeout=_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as exc:
        raise ValueError(f"SimpleFIN fetch failed: {exc}")
    except ValueError:
        raise ValueError("SimpleFIN returned invalid JSON")
    errors = payload.get("errors") or []
    if errors:
        raise ValueError("SimpleFIN error: " + "; ".join(str(e) for e in errors))
    return payload.get("accounts", [])


def list_bank_accounts(user_name: str) -> list[dict]:
    """Bank accounts (no transaction history) for the mapping UI."""
    accounts = fetch_accounts(user_name, start_ts=int(_now().timestamp()))
    return [
        {
            "id": a.get("id"),
            "name": a.get("name") or "Account",
            "org": (a.get("org") or {}).get("name") or (a.get("org") or {}).get("domain") or "",
            "currency": a.get("currency") or "USD",
            "balance_cents": amount_to_cents(a.get("balance")),
        }
        for a in accounts
    ]


def amount_to_cents(value) -> int | None:
    """SimpleFIN sends decimal strings — parse with Decimal, never float."""
    if value is None:
        return None
    try:
        return int((Decimal(str(value)) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


# ---------------------------------------------------------------------------
# Account mapping
# ---------------------------------------------------------------------------


def resolve_target_store(owner: str, target: dict) -> tuple[str, str]:
    """Map a target record to (store_user, workspace)."""
    store = target.get("store", "self")
    if store == "self":
        ws = target.get("workspace", "personal")
        if ws not in ("personal", "business"):
            raise ValueError("Invalid target workspace")
        return owner, ws
    if store == "household":
        return finance_service.POOL_HOUSEHOLD, "personal"
    if store == "team":
        return finance_service.POOL_TEAM, "business"
    raise ValueError("Invalid target store")


def set_mapping(user_name: str, entries: list[dict], is_admin: bool) -> dict:
    """Replace the connection's account map. Pool targets require admin."""
    conn = get_connection(user_name)
    if not conn:
        raise ValueError("No SimpleFIN connection")
    old_by_key = {e.get("simplefin_account_id"): e for e in conn.get("account_map", [])}
    cleaned = []
    for entry in entries:
        sf_id = (entry.get("simplefin_account_id") or "").strip()
        if not sf_id:
            raise ValueError("Missing simplefin_account_id")
        target = entry.get("target") or {}
        if target.get("store") not in VALID_TARGET_STORES:
            raise ValueError("Invalid target store")
        if target["store"] in ("household", "team") and not is_admin:
            raise PermissionError("Only admins can feed a shared pool book from a bank account")
        store_user, ws = resolve_target_store(user_name, target)
        book = finance_service.get_book(store_user, ws, target.get("book_id") or "")
        if not book:
            raise ValueError("Target book not found")
        if not any(a["id"] == target.get("account_id") for a in book.get("accounts", [])):
            raise ValueError(f"Target account not found in book {book['name']!r}")
        cleaned.append(
            {
                "simplefin_account_id": sf_id,
                "bank_name": (entry.get("bank_name") or "")[:80],
                "account_name": (entry.get("account_name") or "")[:80],
                "target": {
                    "store": target["store"],
                    "workspace": target.get("workspace", "personal"),
                    "book_id": target["book_id"],
                    "account_id": target["account_id"],
                },
                "enabled": bool(entry.get("enabled", True)),
                "last_synced_ts": old_by_key.get(sf_id, {}).get("last_synced_ts"),
            }
        )
    conn["account_map"] = cleaned
    save_connection(user_name, conn)
    return connection_status(user_name)


# ---------------------------------------------------------------------------
# Sync engine
# ---------------------------------------------------------------------------


def sync_user(user_name: str, notify_on_error: bool = True) -> dict:
    """Pull transactions for every enabled mapping entry. Returns a summary."""
    conn = get_connection(user_name)
    if not conn:
        return {"error": "not connected"}
    entries = [e for e in conn.get("account_map", []) if e.get("enabled", True)]
    if not entries:
        return {"created": 0, "skipped": 0, "note": "no mapped accounts"}

    now_ts = int(_now().timestamp())
    known = [e["last_synced_ts"] for e in entries if e.get("last_synced_ts")]
    if known:
        start_ts = min(known) - _OVERLAP_DAYS * 86400
    else:
        start_ts = now_ts - _FIRST_SYNC_DAYS * 86400

    try:
        bank_accounts = fetch_accounts(user_name, start_ts=start_ts)
    except ValueError as exc:
        _record_error(user_name, conn, str(exc), notify_on_error)
        return {"error": str(exc)}

    by_id = {a.get("id"): a for a in bank_accounts}
    created = 0
    skipped = 0
    errors: list[str] = []

    for entry in entries:
        bank = by_id.get(entry["simplefin_account_id"])
        if not bank:
            errors.append(
                f"Bank account {entry.get('account_name') or entry['simplefin_account_id']} not in feed"
            )
            continue
        try:
            c, s = _sync_entry(user_name, entry, bank)
            created += c
            skipped += s
            entry["last_synced_ts"] = now_ts
        except ValueError as exc:
            errors.append(str(exc))

    conn["last_sync"] = _now().isoformat()
    if errors:
        conn["last_error"] = "; ".join(errors)[:500]
    else:
        conn["last_error"] = None
        conn["error_notified_at"] = None
    save_connection(user_name, conn)

    if errors and notify_on_error:
        _record_error(user_name, conn, conn["last_error"], True, already_saved=True)

    result = {"created": created, "skipped": skipped}
    if errors:
        result["errors"] = errors
    return result


def _sync_entry(user_name: str, entry: dict, bank: dict) -> tuple[int, int]:
    """Import one bank account's transactions into its mapped finance account."""
    target = entry["target"]
    store_user, ws = resolve_target_store(user_name, target)
    book = finance_service.get_book(store_user, ws, target["book_id"])
    if not book:
        raise ValueError(f"Mapped book for {entry.get('account_name')} no longer exists")
    if not any(a["id"] == target["account_id"] for a in book.get("accounts", [])):
        raise ValueError(f"Mapped account for {entry.get('account_name')} no longer exists")

    seen_sf_ids, _hashes = finance_service.existing_dedup_keys(store_user, ws, book["id"])
    new_txs = []
    skipped = 0
    for tx in bank.get("transactions", []):
        sf_id = tx.get("id")
        if not sf_id or sf_id in seen_sf_ids:
            skipped += 1
            continue
        cents = amount_to_cents(tx.get("amount"))
        if cents is None or cents == 0:
            skipped += 1
            continue
        posted = tx.get("posted") or tx.get("transacted_at")
        try:
            tx_date = datetime.fromtimestamp(int(posted), tz=timezone.utc).date().isoformat()
        except (TypeError, ValueError, OSError):
            skipped += 1
            continue
        payee = (tx.get("payee") or tx.get("description") or "").strip()
        new_txs.append(
            {
                "date": tx_date,
                "amount_cents": cents,
                "account_id": target["account_id"],
                "category": finance_service.apply_rules(store_user, ws, book, payee),
                "payee": payee,
                "notes": (tx.get("memo") or "").strip(),
                "simplefin_id": sf_id,
                "pending": bool(tx.get("pending", False)),
            }
        )
        seen_sf_ids.add(sf_id)

    created_records: list[dict] = []
    if new_txs:
        created_records = finance_service.bulk_add_transactions(
            store_user, ws, book["id"], new_txs, created_by=user_name, source="simplefin"
        )

    finance_service.set_account_sync_state(
        store_user,
        ws,
        book["id"],
        target["account_id"],
        amount_to_cents(bank.get("balance")),
        simplefin_account_id=entry["simplefin_account_id"],
    )

    # Planning hooks: bill matching + budget alerts on the new transactions,
    # then the deviation check against the just-recorded bank balance.
    from services import finance_planning_service

    if created_records:
        finance_planning_service.on_transactions_added(store_user, ws, book["id"], created_records)
    fresh = finance_service.get_book(store_user, ws, book["id"])
    if fresh:
        finance_planning_service.check_deviation(store_user, ws, fresh)
    return len(new_txs), skipped


def _record_error(
    user_name: str, conn: dict, message: str, notify: bool, already_saved: bool = False
) -> None:
    """Persist the failure and notify the user + admins, at most once per day."""
    if not already_saved:
        conn["last_error"] = message[:500]
        save_connection(user_name, conn)
    if not notify:
        return
    last = conn.get("error_notified_at")
    if last:
        try:
            if _now() - datetime.fromisoformat(last) < _ERROR_NOTIFY_EVERY:
                return
        except ValueError:
            pass
    conn["error_notified_at"] = _now().isoformat()
    save_connection(user_name, conn)
    try:
        from services import auth_service
        from services.suggestions_service import notify_user

        recipients = {user_name}
        recipients.update(u["name"] for u in auth_service.list_users() if u.get("role") == "admin")
        for name in recipients:
            notify_user(
                name,
                "⚠️ Bank sync problem",
                f"SimpleFIN sync for {user_name} failed: {message[:200]}",
                source="finance",
                url="/admin",
            )
    except Exception:
        logger.exception("bank-sync error notification failed")


def sync_all_users() -> dict:
    """Scheduler entry point — sync every user that has a connection."""
    from services import auth_service

    totals = {"users": 0, "created": 0, "errors": 0}
    for user in auth_service.list_users():
        name = user["name"]
        if not simplefin_path(name).exists():
            continue
        totals["users"] += 1
        result = sync_user(name)
        totals["created"] += result.get("created", 0)
        if result.get("error") or result.get("errors"):
            totals["errors"] += 1
    return totals
