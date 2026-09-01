"""Tests for services/ai_usage_service.py."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from services import ai_usage_service as svc
from services.auth_service import create_user, today_for_user

USER = "TestUser"


# ---------------------------------------------------------------------------
# period_key / period_range
# ---------------------------------------------------------------------------


def test_period_key_daily():
    d = date(2026, 7, 30)
    assert svc._period_key(d, "daily") == "2026-07-30"


def test_period_key_monthly():
    d = date(2026, 7, 30)
    assert svc._period_key(d, "monthly") == "2026-07"


def test_period_key_weekly_iso():
    # 2026-07-30 is a Thursday in ISO week 31
    d = date(2026, 7, 30)
    assert svc._period_key(d, "weekly") == "2026-W31"


def test_period_range_weekly_spans_monday_to_sunday():
    d = date(2026, 7, 30)  # Thursday
    start, end = svc._period_range(d, "weekly")
    assert start == date(2026, 7, 27)  # Monday
    assert end == date(2026, 8, 2)  # Sunday


def test_period_range_monthly_handles_december():
    start, end = svc._period_range(date(2026, 12, 15), "monthly")
    assert start == date(2026, 12, 1)
    assert end == date(2026, 12, 31)


# ---------------------------------------------------------------------------
# record_tokens / record_message
# ---------------------------------------------------------------------------


def test_record_tokens_accumulates_personal_and_business(brain):
    svc.record_tokens(USER, "personal", 100, 50)
    svc.record_tokens(USER, "business", 10, 5)

    data = svc._load()
    # USER isn't registered here, so it has no stored timezone and the service
    # buckets by UTC (today_for_user's fallback) — must match that basis, not
    # bare date.today() (local), or this flakes for a few hours every day
    # whenever UTC has already rolled to the next date and local hasn't.
    today = today_for_user(USER).isoformat()
    day = data["users"][USER]["days"][today]
    assert day["personal"] == {"messages": 0, "input_tokens": 100, "output_tokens": 50}
    assert day["business"] == {"messages": 0, "input_tokens": 10, "output_tokens": 5}


def test_record_tokens_zero_is_a_noop(brain):
    svc.record_tokens(USER, "personal", 0, 0)
    data = svc._load()
    assert USER not in data["users"]


def test_record_message_only_bumps_messages(brain):
    svc.record_message(USER, "personal")
    data = svc._load()
    # Same basis as test_record_tokens_accumulates_personal_and_business above.
    today = today_for_user(USER).isoformat()
    day = data["users"][USER]["days"][today]
    assert day["personal"]["messages"] == 1
    assert day["personal"]["input_tokens"] == 0


# ---------------------------------------------------------------------------
# check_usage / accept_overage
# ---------------------------------------------------------------------------


def test_check_usage_ok_by_default(brain):
    assert svc.check_usage(USER) == {"status": "ok"}


def test_check_usage_blocked_for_hard_mode_over_limit(brain):
    svc.set_user_limits(USER, {"mode": "hard", "token_limit": 100})
    svc.record_tokens(USER, "personal", 80, 80)  # 160 > 100
    assert svc.check_usage(USER) == {"status": "blocked"}


def test_check_usage_soft_confirm_then_accept(brain):
    svc.set_user_limits(USER, {"mode": "soft", "message_limit": 2})
    svc.record_message(USER, "personal")
    svc.record_message(USER, "personal")  # at limit

    assert svc.check_usage(USER) == {"status": "soft_confirm"}

    svc.accept_overage(USER)
    assert svc.check_usage(USER) == {"status": "ok"}

    # A third message still counts, and the acceptance still holds this period.
    svc.record_message(USER, "personal")
    assert svc.check_usage(USER) == {"status": "ok"}


def test_off_mode_never_blocked_regardless_of_limits(brain):
    svc.set_user_limits(USER, {"mode": "off", "message_limit": 1})
    svc.record_message(USER, "personal")
    svc.record_message(USER, "personal")
    svc.record_message(USER, "personal")
    assert svc.check_usage(USER) == {"status": "ok"}


# ---------------------------------------------------------------------------
# warn/over escalation — fires once per period, never re-fires
# ---------------------------------------------------------------------------


def test_warn_and_over_escalate_once_each(brain, monkeypatch):
    notify = MagicMock()
    monkeypatch.setattr("services.suggestions_service.notify_user", notify)

    svc.set_user_limits(USER, {"mode": "soft", "message_limit": 10, "period": "daily"})

    # 8/10 = 80% -> warn (default warn_pct)
    for _ in range(8):
        svc.record_message(USER, "personal")
    assert notify.call_count == 1
    assert notify.call_args[0][1] == "Approaching AI usage limit"

    # Still under 100% -> no re-fire
    svc.record_message(USER, "personal")  # 9/10
    assert notify.call_count == 1

    # Cross 100% -> over, fires once
    svc.record_message(USER, "personal")  # 10/10
    assert notify.call_count == 2
    assert notify.call_args[0][1] == "AI usage limit reached"

    # Further usage past "over" must not re-fire
    svc.record_message(USER, "personal")
    assert notify.call_count == 2


def test_hard_over_notifies_admins_too(brain, monkeypatch):
    create_user("admin@example.com", "password123", "AdminUser", role="admin")
    notify = MagicMock()
    monkeypatch.setattr("services.suggestions_service.notify_user", notify)

    svc.set_user_limits(USER, {"mode": "hard", "message_limit": 1})
    svc.record_message(USER, "personal")

    names_notified = [c.args[0] for c in notify.call_args_list]
    assert USER in names_notified
    assert "AdminUser" in names_notified


# ---------------------------------------------------------------------------
# get_my_usage
# ---------------------------------------------------------------------------


def test_get_my_usage_off_mode(brain):
    result = svc.get_my_usage(USER)
    assert result["mode"] == "off"
    assert result["pct"] is None


def test_get_my_usage_pct_is_max_of_message_and_token_ratio(brain):
    svc.set_user_limits(USER, {"mode": "soft", "message_limit": 100, "token_limit": 1000})
    svc.record_tokens(USER, "personal", 400, 100)  # 500/1000 = 50%
    svc.record_message(USER, "personal")  # 1/100 = 1%

    result = svc.get_my_usage(USER)
    assert result["pct"] == 50
    assert result["used_messages"] == 1
    assert result["used_tokens"] == 500


# ---------------------------------------------------------------------------
# defaults / per-user limits
# ---------------------------------------------------------------------------


def test_get_defaults_returns_seeded_values(brain):
    assert svc.get_defaults() == {
        "period": "monthly",
        "message_limit": None,
        "token_limit": None,
        "warn_pct": 80,
    }


def test_set_defaults_merges_partial_updates(brain):
    svc.set_defaults({"token_limit": 5000})
    data = svc._load()
    assert data["defaults"]["token_limit"] == 5000
    assert data["defaults"]["period"] == "monthly"  # untouched
    assert svc.get_defaults()["token_limit"] == 5000


def test_per_user_limit_overrides_default(brain):
    svc.set_defaults({"token_limit": 1000})
    svc.set_user_limits(USER, {"mode": "hard", "token_limit": 50})
    svc.record_tokens(USER, "personal", 60, 0)
    assert svc.check_usage(USER) == {"status": "blocked"}


# ---------------------------------------------------------------------------
# Admin overview / per-user rows
# ---------------------------------------------------------------------------


def test_get_overview_sums_personal_and_business(brain):
    svc.record_tokens(USER, "personal", 100, 10)
    svc.record_tokens(USER, "business", 20, 5)
    svc.record_message(USER, "personal")

    # record_tokens/record_message bucket by today_for_user(), not the system
    # clock's own date.today() — USER isn't a real registered user here, so
    # that resolves to plain UTC. Matching the same basis here (rather than
    # date.today()) keeps this test correct across the UTC-midnight boundary
    # regardless of what timezone the machine running it is in.
    month = today_for_user(USER).strftime("%Y-%m")
    overview = svc.get_overview(month)
    assert overview["personal"]["input_tokens"] == 100
    assert overview["business"]["input_tokens"] == 20
    assert overview["total"]["input_tokens"] == 120
    assert overview["personal"]["messages"] == 1


def test_get_user_rows_includes_every_registered_user(brain):
    create_user("member@example.com", "password123", USER)
    svc.record_message(USER, "personal")

    # Same reasoning as test_get_overview_sums_personal_and_business above:
    # pin the query month to the same basis record_message() wrote under
    # instead of relying on get_user_rows()'s own date.today()-based default,
    # which disagrees with it for a few hours around UTC midnight.
    rows = svc.get_user_rows(today_for_user(USER).strftime("%Y-%m"))
    names = [r["name"] for r in rows]
    assert USER in names
    row = next(r for r in rows if r["name"] == USER)
    assert row["personal"]["messages"] == 1
    assert row["mode"] == "off"
    assert row["status"] == "off"
