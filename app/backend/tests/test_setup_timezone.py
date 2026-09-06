"""Regression test for the demo-login timezone bug: setup_user() used to run
req.timezone through the markdown-safe sanitizer built for free-text fields
like `role`. That regex rejects underscores (treating them as markdown italics
markers), but real IANA timezone identifiers routinely contain them —
America/New_York, America/Los_Angeles, America/Mexico_City, Asia/Hong_Kong —
so any visitor in one of those zones was hard-blocked from ever generating a
demo account. ZoneInfo() already proves the value is a legitimate tzdata
identifier, so it should never hit that sanitizer at all.

setup_user()'s own internals (Brain template copy, self-contact creation,
etc.) are untested anywhere in this suite today and out of scope here, same
as test_auth_demo_login.py — this stubs shutil.copytree to bail out right
after the validation block this bug lives in, so the test only proves that
block's behavior."""

import routers.setup as setup_router
from routers.setup import SetupRequest, setup_user
from services import auth_service


class _PastValidation(Exception):
    """Sentinel raised by the stubbed copytree — proves validation didn't 400."""


def _register(brain):
    return auth_service.create_user("visitor@example.com", "password123", "Visitor")


def _stub_copytree(monkeypatch):
    def _raise(*a, **k):
        raise _PastValidation()

    monkeypatch.setattr(setup_router.shutil, "copytree", _raise)


def test_setup_accepts_timezones_with_underscores(brain, monkeypatch):
    user = _register(brain)
    _stub_copytree(monkeypatch)

    try:
        setup_user(
            SetupRequest(priority_order=["Family"], timezone="America/New_York"),
            current_user=user,
        )
        assert False, "expected the stubbed copytree to run"
    except _PastValidation:
        pass  # validation accepted the underscore-bearing timezone


def test_setup_still_rejects_a_fake_timezone(brain, monkeypatch):
    user = _register(brain)
    _stub_copytree(monkeypatch)

    try:
        setup_user(
            SetupRequest(priority_order=["Family"], timezone="Not/A_Real_Zone"),
            current_user=user,
        )
        assert False, "expected HTTPException for an invalid IANA zone"
    except _PastValidation:
        assert False, "a fake timezone must never reach the copytree step"
    except Exception as e:
        assert "Invalid timezone" in str(e)
