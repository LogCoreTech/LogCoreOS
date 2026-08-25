"""Integration tests for calendar's conversion into module_packages/
(increment — Calendar, 2026-08-25) — not events_service's own CRUD logic
(untested even before this conversion — events_service.py stays in core,
shared with Household/Team, and remains an existing coverage gap), but the
surrounding machinery: the m020 upgrade migration (features.json-existence
guard, same idiom as journal's m015/automations' m019 — calendar was
always-on before this system existed, unlike Home Assistant's opt-in
ha_config.json guard), and a full install/uninstall/reinstall round-trip
through the real Mod Store service."""

from migrations.runner import run_pending
from services import mod_store_service


def test_m020_marks_calendar_installed_on_upgrade(brain):
    """An existing instance (has _system/features.json from a prior setup)
    had calendar permanently on — upgrading must not silently take the
    feature away."""
    (brain / "_system" / "features.json").write_text('{"profile": "personal", "roles": {}}')

    run_pending(brain)

    assert mod_store_service.is_installed("calendar")


def test_m020_noop_on_fresh_install(brain):
    """No _system/features.json yet means this Brain never went through the
    always-on-calendar era — it should start with calendar NOT installed,
    matching the actual goal of slimming the default install."""
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("calendar")


def test_install_uninstall_reinstall_round_trip_preserves_data(brain):
    """The real end-to-end guarantee: uninstalling calendar never touches
    its data, and reinstalling picks it back up immediately."""
    from services import events_service

    events_service.add_event("dana", {"title": "Standup", "start_date": "2026-09-01"})

    mod_store_service.mark_installed("calendar", by="tester")
    assert mod_store_service.is_installed("calendar")

    mod_store_service.mark_uninstalled("calendar", by="tester")
    assert not mod_store_service.is_installed("calendar")
    # data untouched even while "uninstalled"
    assert events_service.list_events("dana")[0]["title"] == "Standup"

    mod_store_service.mark_installed("calendar", by="tester")
    assert mod_store_service.is_installed("calendar")
    assert events_service.list_events("dana")[0]["title"] == "Standup"


def test_household_calendar_is_independent_of_calendar_module_state(brain):
    """The real guarantee behind this conversion being safe to ship at all:
    Household's/Team's own pool calendars are gated by require_module
    ("household")/("team") only, never require_module("calendar") — so
    uninstalling the personal Calendar module must never affect them.
    Exercised here at the service layer (events_service is shared, storage
    is keyed by store_user, not by any module-install flag) since the
    actual gating is a router-level Depends(), covered by existing
    Household/Team router tests instead of duplicated here."""
    from services import events_service

    events_service.add_event("_household", {"title": "Family dinner", "start_date": "2026-09-02"})

    mod_store_service.mark_uninstalled("calendar", by="tester")
    assert not mod_store_service.is_installed("calendar")

    assert events_service.list_events("_household")[0]["title"] == "Family dinner"
