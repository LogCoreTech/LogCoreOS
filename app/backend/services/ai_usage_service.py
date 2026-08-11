"""AI usage metering + caps.

Tracks messages/tokens per user per day in brain/_system/ai_usage.json —
operational metadata, never part of a user's portable Brain folder. Daily/
weekly/monthly totals are always derived on read by summing the day buckets
in the right date range; nothing is pre-aggregated, so switching a user's
cap period needs no migration.

The three real AI call sites (chat, save-memory, custom AI suggestions) call
record_tokens()/record_message() after a successful provider response, and
check_usage() before spending anything. This module never raises out of the
record_* functions on a bad input — a metering bug must never break a real
AI call.
"""

import threading
from datetime import date, timedelta
from pathlib import Path

from config import settings
from services.auth_service import today_for_user
from services.file_service import read_json, write_json

_usage_lock = threading.Lock()

_DEFAULT_DEFAULTS = {
    "period": "monthly",
    "message_limit": None,
    "token_limit": None,
    "warn_pct": 80,
}


def _path() -> Path:
    return settings.brain_path / "_system" / "ai_usage.json"


def _load() -> dict:
    data = read_json(_path(), default={})
    data.setdefault("defaults", dict(_DEFAULT_DEFAULTS))
    data.setdefault("users", {})
    return data


def _save(data: dict) -> None:
    write_json(_path(), data)


def _new_user() -> dict:
    return {
        "period": None,
        "mode": "off",
        "message_limit": None,
        "token_limit": None,
        "soft_accepted_period": None,
        "alert_state": {},
        "days": {},
    }


def _new_day() -> dict:
    return {
        "personal": {"messages": 0, "input_tokens": 0, "output_tokens": 0},
        "business": {"messages": 0, "input_tokens": 0, "output_tokens": 0},
    }


def _ws_key(workspace: str) -> str:
    return "business" if workspace == "business" else "personal"


# ---------------------------------------------------------------------------
# Period resolution — daily/weekly/monthly, all derived from day buckets
# ---------------------------------------------------------------------------


def _period_key(today: date, period: str) -> str:
    if period == "daily":
        return today.isoformat()
    if period == "weekly":
        iso = today.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return today.strftime("%Y-%m")


def _period_range(today: date, period: str) -> tuple[date, date]:
    if period == "daily":
        return today, today
    if period == "weekly":
        start = today - timedelta(days=today.weekday())  # Monday
        return start, start + timedelta(days=6)
    start = today.replace(day=1)
    next_month = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, next_month - timedelta(days=1)


def _month_range(month: str) -> tuple[date, date]:
    start = date.fromisoformat(f"{month}-01")
    next_month = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, next_month - timedelta(days=1)


def _sum_range(user_entry: dict, start: date, end: date) -> dict:
    """Sum personal + business day buckets between start and end (inclusive)."""
    personal = {"messages": 0, "input_tokens": 0, "output_tokens": 0}
    business = {"messages": 0, "input_tokens": 0, "output_tokens": 0}
    for day_key, day in user_entry.get("days", {}).items():
        try:
            d = date.fromisoformat(day_key)
        except ValueError:
            continue
        if start <= d <= end:
            for k in ("messages", "input_tokens", "output_tokens"):
                personal[k] += day.get("personal", {}).get(k, 0)
                business[k] += day.get("business", {}).get(k, 0)
    return {"personal": personal, "business": business}


def _combined_totals(breakdown: dict) -> dict:
    messages = breakdown["personal"]["messages"] + breakdown["business"]["messages"]
    tokens = (
        breakdown["personal"]["input_tokens"]
        + breakdown["personal"]["output_tokens"]
        + breakdown["business"]["input_tokens"]
        + breakdown["business"]["output_tokens"]
    )
    return {"messages": messages, "tokens": tokens}


def _effective(user_entry: dict, defaults: dict) -> dict:
    return {
        "period": user_entry.get("period") or defaults.get("period", "monthly"),
        "mode": user_entry.get("mode", "off"),
        "message_limit": (
            user_entry["message_limit"]
            if user_entry.get("message_limit") is not None
            else defaults.get("message_limit")
        ),
        "token_limit": (
            user_entry["token_limit"]
            if user_entry.get("token_limit") is not None
            else defaults.get("token_limit")
        ),
        "warn_pct": defaults.get("warn_pct", 80),
    }


def _status(messages: int, tokens: int, eff: dict) -> str:
    ratios = []
    if eff["message_limit"]:
        ratios.append(messages / eff["message_limit"])
    if eff["token_limit"]:
        ratios.append(tokens / eff["token_limit"])
    if not ratios:
        return "ok"
    worst = max(ratios)
    if worst >= 1.0:
        return "over"
    if worst >= eff["warn_pct"] / 100:
        return "warn"
    return "ok"


# ---------------------------------------------------------------------------
# Recording — called after a successful AI provider response
# ---------------------------------------------------------------------------


def _bump_and_escalate(data: dict, user_name: str, mutate) -> tuple[str, str, str] | None:
    """Apply `mutate(day_bucket)`, then check for a new warn/over escalation.

    Returns (status, mode, period) if this call crossed a NEW threshold for
    the current period, else None. Caller notifies outside the file lock.
    """
    u = data["users"].setdefault(user_name, _new_user())
    today = today_for_user(user_name)
    day = u["days"].setdefault(today.isoformat(), _new_day())
    mutate(day)

    eff = _effective(u, data["defaults"])
    if eff["mode"] == "off":
        return None

    pkey = _period_key(today, eff["period"])
    start, end = _period_range(today, eff["period"])
    totals = _combined_totals(_sum_range(u, start, end))
    status = _status(totals["messages"], totals["tokens"], eff)

    prev = u["alert_state"].get(pkey, "none")
    if status == "over" and prev != "over":
        u["alert_state"][pkey] = "over"
        return ("over", eff["mode"], eff["period"])
    if status == "warn" and prev == "none":
        u["alert_state"][pkey] = "warn"
        return ("warn", eff["mode"], eff["period"])
    return None


def record_tokens(user_name: str, workspace: str, input_tokens: int, output_tokens: int) -> None:
    if input_tokens <= 0 and output_tokens <= 0:
        return
    ws = _ws_key(workspace)

    def mutate(day: dict) -> None:
        day[ws]["input_tokens"] += input_tokens
        day[ws]["output_tokens"] += output_tokens

    with _usage_lock:
        data = _load()
        escalation = _bump_and_escalate(data, user_name, mutate)
        _save(data)

    if escalation:
        _notify_escalation(user_name, *escalation)


def record_message(user_name: str, workspace: str) -> None:
    ws = _ws_key(workspace)

    def mutate(day: dict) -> None:
        day[ws]["messages"] += 1

    with _usage_lock:
        data = _load()
        escalation = _bump_and_escalate(data, user_name, mutate)
        _save(data)

    if escalation:
        _notify_escalation(user_name, *escalation)


def _notify_escalation(user_name: str, status: str, mode: str, period: str) -> None:
    from services.auth_service import list_users
    from services.suggestions_service import notify_user

    if status == "warn":
        notify_user(
            user_name,
            "Approaching AI usage limit",
            f"You're near your AI usage limit for this {period}.",
            "ai_usage",
        )
        return

    if mode == "hard":
        notify_user(
            user_name,
            "AI usage limit reached",
            "AI usage is paused until your admin raises the limit.",
            "ai_usage",
        )
        for admin in list_users():
            if admin.get("role") == "admin":
                notify_user(
                    admin["name"],
                    "AI usage cap hit",
                    f"{user_name} hit their hard AI usage cap for this {period}.",
                    "ai_usage",
                )
    elif mode == "soft":
        notify_user(
            user_name,
            "AI usage limit reached",
            f"You've reached your AI usage limit for this {period} — your next "
            "message will ask you to confirm before continuing.",
            "ai_usage",
        )


# ---------------------------------------------------------------------------
# Gating — called before spending anything
# ---------------------------------------------------------------------------


def check_usage(user_name: str) -> dict:
    data = _load()
    u = data["users"].get(user_name)
    if not u:
        return {"status": "ok"}

    eff = _effective(u, data["defaults"])
    if eff["mode"] == "off":
        return {"status": "ok"}

    today = today_for_user(user_name)
    pkey = _period_key(today, eff["period"])
    start, end = _period_range(today, eff["period"])
    totals = _combined_totals(_sum_range(u, start, end))
    status = _status(totals["messages"], totals["tokens"], eff)

    if status != "over":
        return {"status": "ok"}
    if eff["mode"] == "hard":
        return {"status": "blocked"}
    if u.get("soft_accepted_period") == pkey:
        return {"status": "ok"}
    return {"status": "soft_confirm"}


def accept_overage(user_name: str) -> None:
    with _usage_lock:
        data = _load()
        u = data["users"].setdefault(user_name, _new_user())
        eff = _effective(u, data["defaults"])
        today = today_for_user(user_name)
        u["soft_accepted_period"] = _period_key(today, eff["period"])
        _save(data)


def get_my_usage(user_name: str) -> dict:
    """Self-service usage summary for the Chat module's usage indicator."""
    data = _load()
    u = data["users"].get(user_name, _new_user())
    eff = _effective(u, data["defaults"])

    if eff["mode"] == "off":
        return {
            "mode": "off",
            "period": eff["period"],
            "message_limit": None,
            "token_limit": None,
            "used_messages": 0,
            "used_tokens": 0,
            "pct": None,
        }

    today = today_for_user(user_name)
    start, end = _period_range(today, eff["period"])
    totals = _combined_totals(_sum_range(u, start, end))

    ratios = []
    if eff["message_limit"]:
        ratios.append(totals["messages"] / eff["message_limit"] * 100)
    if eff["token_limit"]:
        ratios.append(totals["tokens"] / eff["token_limit"] * 100)
    pct = round(max(ratios)) if ratios else None

    return {
        "mode": eff["mode"],
        "period": eff["period"],
        "message_limit": eff["message_limit"],
        "token_limit": eff["token_limit"],
        "used_messages": totals["messages"],
        "used_tokens": totals["tokens"],
        "pct": pct,
    }


# ---------------------------------------------------------------------------
# Admin — overview, per-user rows, defaults, per-user limits
# ---------------------------------------------------------------------------


def get_overview(month: str | None = None) -> dict:
    data = _load()
    month = month or date.today().strftime("%Y-%m")
    start, end = _month_range(month)

    personal = {"messages": 0, "input_tokens": 0, "output_tokens": 0}
    business = {"messages": 0, "input_tokens": 0, "output_tokens": 0}
    months_seen: set[str] = set()

    for u in data["users"].values():
        for day_key in u.get("days", {}):
            months_seen.add(day_key[:7])
        breakdown = _sum_range(u, start, end)
        for k in ("messages", "input_tokens", "output_tokens"):
            personal[k] += breakdown["personal"][k]
            business[k] += breakdown["business"][k]

    total = {k: personal[k] + business[k] for k in personal}
    return {
        "month": month,
        "personal": personal,
        "business": business,
        "total": total,
        "available_months": sorted(months_seen, reverse=True),
    }


def get_user_rows(month: str | None = None) -> list[dict]:
    from services.auth_service import list_users

    data = _load()
    month = month or date.today().strftime("%Y-%m")
    start, end = _month_range(month)

    rows = []
    for user in list_users():
        name = user["name"]
        u = data["users"].get(name, _new_user())
        breakdown = _sum_range(u, start, end)

        eff = _effective(u, data["defaults"])
        if eff["mode"] == "off":
            status = "off"
        else:
            today = today_for_user(name)
            p_start, p_end = _period_range(today, eff["period"])
            totals = _combined_totals(_sum_range(u, p_start, p_end))
            status = _status(totals["messages"], totals["tokens"], eff)

        rows.append(
            {
                "user_id": user["id"],
                "name": name,
                "personal": breakdown["personal"],
                "business": breakdown["business"],
                "period": eff["period"],
                "mode": eff["mode"],
                "message_limit": eff["message_limit"],
                "token_limit": eff["token_limit"],
                "status": status,
            }
        )
    return rows


def get_defaults() -> dict:
    return dict(_load()["defaults"])


def set_defaults(updates: dict) -> dict:
    with _usage_lock:
        data = _load()
        data["defaults"].update(updates)
        _save(data)
        return dict(data["defaults"])


def set_user_limits(user_name: str, updates: dict) -> dict:
    with _usage_lock:
        data = _load()
        u = data["users"].setdefault(user_name, _new_user())
        u.update(updates)
        _save(data)
        return {
            "period": u["period"],
            "mode": u["mode"],
            "message_limit": u["message_limit"],
            "token_limit": u["token_limit"],
        }
