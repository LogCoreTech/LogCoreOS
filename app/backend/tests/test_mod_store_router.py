"""Tests for routers/mod_store.py's actual endpoint functions — install,
uninstall, and especially restart, which had zero router-level coverage
before this file (test_mod_store_service.py only exercises the service
layer; test_journal_module_conversion.py drives mark_installed/
mark_uninstalled directly, never the router).

restart() is the important one: it restarts the app's OWN container, so the
Docker call can never run inline in the request handler — see docs/MEMORY.md
(2026-08-24, mod store reinstall crash) for why. The regression this guards
against: an earlier version called container.restart() synchronously before
returning, which could kill the process before the HTTP response reached the
client.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from routers.mod_store import RestartRequest, install, restart, uninstall
from services import auth_service, mod_store_service


@pytest.fixture(autouse=True)
def _reset_catalog_cache():
    mod_store_service._cache = None
    yield
    mod_store_service._cache = None


@pytest.fixture()
def admin(brain):
    return auth_service.create_user("admin@example.com", "password123", "Admin", role="admin")


@pytest.fixture()
def fake_docker(monkeypatch):
    """Stubs the `import docker as docker_sdk` local import inside restart()
    with a fake client whose containers.get(...).restart() is a plain Mock —
    tests assert on when it's called, never touching a real Docker daemon."""
    fake_container = MagicMock()
    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container
    monkeypatch.setitem(sys.modules, "docker", types.SimpleNamespace(from_env=lambda: fake_client))

    import routers.mod_store as mod_store_router

    monkeypatch.setattr(mod_store_router.time, "sleep", lambda seconds: None)
    return fake_container


def test_restart_defers_container_restart_to_a_background_task(admin, fake_docker):
    """The actual regression test: restart() must return without having
    touched the container yet — only once the deferred task actually runs
    should container.restart() fire. Calling it inline (the old bug) would
    have failed this test's first assertion, since the fake would already be
    called by the time restart() returns."""
    bg = BackgroundTasks()

    result = restart(RestartRequest(force=False), bg, admin)

    assert result == {"ok": True, "restarting": True}
    fake_docker.restart.assert_not_called()

    assert len(bg.tasks) == 1
    bg.tasks[0].func(*bg.tasks[0].args, **bg.tasks[0].kwargs)
    fake_docker.restart.assert_called_once()


def test_restart_fails_fast_and_synchronously_on_docker_connection_error(admin, monkeypatch):
    """A real config/permission problem (socket-proxy unreachable, wrong
    container name) must surface to the client immediately as a 502 — not
    get swallowed by the background task where only server logs would ever
    show it."""
    def _broken_from_env():
        raise RuntimeError("cannot reach docker socket")

    monkeypatch.setitem(sys.modules, "docker", types.SimpleNamespace(from_env=_broken_from_env))
    bg = BackgroundTasks()

    with pytest.raises(HTTPException) as exc:
        restart(RestartRequest(force=False), bg, admin)

    assert exc.value.status_code == 502
    assert len(bg.tasks) == 0


def test_restart_blocks_on_other_online_users_unless_forced(admin, fake_docker, monkeypatch):
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    monkeypatch.setattr("routers.mod_store.list_users", lambda: [admin, bob])
    monkeypatch.setattr("routers.mod_store.presence_service.is_online", lambda name: name == "Bob")

    bg = BackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        restart(RestartRequest(force=False), bg, admin)
    assert exc.value.status_code == 409
    assert exc.value.detail["online_users"] == ["Bob"]
    assert len(bg.tasks) == 0

    # force=True bypasses the same conflict and proceeds to defer the restart
    bg2 = BackgroundTasks()
    result = restart(RestartRequest(force=True), bg2, admin)
    assert result == {"ok": True, "restarting": True}
    assert len(bg2.tasks) == 1


def test_install_unknown_module_404(admin, brain):
    with pytest.raises(HTTPException) as exc:
        install("t_does_not_exist", admin)
    assert exc.value.status_code == 404


def test_install_already_installed_409(admin, brain):
    mod_store_service.mark_installed("journal", by=admin["name"])
    with pytest.raises(HTTPException) as exc:
        install("journal", admin)
    assert exc.value.status_code == 409


def test_install_success_marks_installed_and_runs_on_install(admin, brain):
    """The on_install hook itself (folder backfill for real users) is covered
    in detail by test_journal_module_conversion.py — this just confirms the
    router actually invokes it and marks the module installed, rather than
    skipping straight to the marker flip."""
    assert not mod_store_service.is_installed("journal")

    result = install("journal", admin)

    assert result == {"ok": True, "module_id": "journal", "restart_required": True}
    assert mod_store_service.is_installed("journal")


def test_uninstall_not_installed_404(admin, brain):
    with pytest.raises(HTTPException) as exc:
        uninstall("journal", admin)
    assert exc.value.status_code == 404


def test_uninstall_success(admin, brain):
    mod_store_service.mark_installed("journal", by=admin["name"])

    result = uninstall("journal", admin)

    assert result == {"ok": True, "module_id": "journal", "restart_required": True}
    assert not mod_store_service.is_installed("journal")


def test_reinstall_after_uninstall_succeeds_through_the_router(admin, brain):
    """The exact sequence reported as crashing in production: install,
    uninstall, then install again — all through the real router functions,
    not just the service layer."""
    assert install("journal", admin)["ok"] is True
    assert uninstall("journal", admin)["ok"] is True

    result = install("journal", admin)

    assert result["ok"] is True
    assert mod_store_service.is_installed("journal")
