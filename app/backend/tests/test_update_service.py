"""Tests for services/update_service.py's resync flag mechanism and
routers/update.py's /resync endpoint. First test coverage for this file —
resync is new (2026-09-01), everything else here (status/apply/log/settings)
was previously untested too; this file only covers what's touched by this
change, not a full retroactive backfill.

Endpoint functions called directly, bypassing Depends(...), matching this
suite's established convention (see test_mod_store_router.py)."""

from fastapi import HTTPException

from routers.update import resync_update
from services import update_service as svc


def test_trigger_resync_writes_the_flag_file(brain):
    assert not (brain / "_system" / "pending_resync").exists()
    result = svc.trigger_resync()
    assert result == {"triggered": True}
    assert (brain / "_system" / "pending_resync").exists()


def test_status_reports_resync_pending(brain):
    assert svc.get_update_status()["resync_pending"] is False
    svc.trigger_resync()
    assert svc.get_update_status()["resync_pending"] is True


def test_resync_pending_is_independent_of_update_pending(brain):
    svc.trigger_update()
    status = svc.get_update_status()
    assert status["update_pending"] is True
    assert status["resync_pending"] is False


def test_resync_endpoint_writes_the_flag(brain):
    result = resync_update({"role": "admin"})
    assert result == {"triggered": True}
    assert (brain / "_system" / "pending_resync").exists()


def test_resync_endpoint_409s_if_update_running(brain):
    (brain / "_system").mkdir(parents=True, exist_ok=True)
    (brain / "_system" / "update_running").write_text("x")
    try:
        resync_update({"role": "admin"})
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 409
    assert not (brain / "_system" / "pending_resync").exists()


def test_resync_endpoint_409s_if_update_already_pending(brain):
    svc.trigger_update()
    try:
        resync_update({"role": "admin"})
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 409
    assert not (brain / "_system" / "pending_resync").exists()
