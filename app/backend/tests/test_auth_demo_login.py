"""Tests for routers/auth.py's demo_login() — the one-click account for a public
demo instance. setup_user()'s own internals (Brain template copy, self-contact
creation, etc.) are untested anywhere in this suite today and out of scope here;
these tests stub it out and assert demo_login() calls it correctly, the same way
test_mod_store_router.py stubs a local import rather than re-proving that
import's own target. Endpoint called directly, bypassing Depends(...), matching
this suite's established convention (see test_mod_store_router.py /
module_packages/household/tests/test_household_router.py)."""

from fastapi import HTTPException, Response

import routers.setup as setup_router
from config import settings
from routers.auth import DemoLoginRequest, demo_login
from services import auth_service


def _stub_setup(monkeypatch):
    calls = []
    monkeypatch.setattr(
        setup_router, "setup_user", lambda req, current_user: calls.append((req, current_user))
    )
    return calls


def test_404s_when_demo_mode_is_off(brain, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    _stub_setup(monkeypatch)

    try:
        demo_login(DemoLoginRequest(timezone="UTC"), Response())
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 404


def test_creates_a_member_account_with_a_generated_name(brain, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    _stub_setup(monkeypatch)

    result = demo_login(DemoLoginRequest(timezone="America/Chicago"), Response())

    assert result["role"] == "member"
    assert len(result["name"].split(" ")) == 2  # "Adjective Noun"
    users = auth_service.list_users()
    assert any(u["name"] == result["name"] for u in users)


def test_sets_the_auth_cookie(brain, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    _stub_setup(monkeypatch)

    response = Response()
    demo_login(DemoLoginRequest(timezone="UTC"), response)

    assert any(h[0] == b"set-cookie" for h in response.raw_headers)


def test_calls_setup_user_with_default_priorities_and_requested_timezone(brain, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    calls = _stub_setup(monkeypatch)

    demo_login(DemoLoginRequest(timezone="America/Chicago"), Response())

    assert len(calls) == 1
    req, current_user = calls[0]
    assert req.priority_order == ["Religion", "Family", "Job", "Personal Growth", "Hobbies"]
    assert req.timezone == "America/Chicago"
    assert req.profile == "personal"
    assert current_user["name"] == auth_service.list_users()[0]["name"]


def test_repeated_calls_create_distinct_accounts(brain, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    _stub_setup(monkeypatch)

    first = demo_login(DemoLoginRequest(timezone="UTC"), Response())
    second = demo_login(DemoLoginRequest(timezone="UTC"), Response())

    assert first["id"] != second["id"]
    assert len(auth_service.list_users()) == 2


def test_never_creates_an_admin_even_as_the_first_user(brain, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    _stub_setup(monkeypatch)
    assert auth_service.user_count() == 0

    result = demo_login(DemoLoginRequest(timezone="UTC"), Response())

    assert result["role"] == "member"
