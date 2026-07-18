"""Tests for the What's-New broadcast: version-bump notification + banner window."""

from datetime import datetime, timedelta, timezone

import services.whats_new_service as wn
from config import settings
from services import help_service
from services.file_service import read_json, write_json


def _set_version(brain, v):
    write_json(brain / "_system" / "installed_version.json", {"version": v})


def _content_with(*versions):
    return {
        "sections": [],
        "faq": [],
        "support": {},
        "whats_new": [
            {"version": v, "date": "2026-01-01", "highlights": [f"hi {v}"]} for v in versions
        ],
    }


def test_fresh_install_sets_baseline_silently(brain, monkeypatch):
    _set_version(brain, "0.3.0")
    calls = []
    monkeypatch.setattr("services.auth_service.list_users", lambda: [{"name": "A"}, {"name": "B"}])
    monkeypatch.setattr("services.suggestions_service.notify_user", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(help_service, "get_content", lambda: _content_with("0.3.0"))

    res = wn.announce_if_updated()
    assert res["announced"] is False and res["reason"] == "baseline"
    assert calls == []
    state = read_json(brain / "_system" / "whats_new_state.json")
    assert state["announced_version"] == "0.3.0"
    assert state["announced_at"] is None


def test_version_bump_notifies_all_users_once(brain, monkeypatch):
    write_json(
        brain / "_system" / "whats_new_state.json",
        {"announced_version": "0.2.0", "announced_at": None},
    )
    _set_version(brain, "0.3.0")
    calls = []
    monkeypatch.setattr("services.auth_service.list_users", lambda: [{"name": "A"}, {"name": "B"}])
    monkeypatch.setattr(
        "services.suggestions_service.notify_user", lambda name, *a, **k: calls.append(name)
    )
    monkeypatch.setattr(help_service, "get_content", lambda: _content_with("0.3.0"))

    res = wn.announce_if_updated()
    assert res["announced"] is True and res["notified"] == 2
    assert set(calls) == {"A", "B"}
    assert read_json(brain / "_system" / "whats_new_state.json")["announced_version"] == "0.3.0"

    # Second boot on the same version: no re-announce.
    res2 = wn.announce_if_updated()
    assert res2["announced"] is False
    assert len(calls) == 2


def test_no_matching_entry_does_not_announce(brain, monkeypatch):
    write_json(
        brain / "_system" / "whats_new_state.json",
        {"announced_version": "0.2.0", "announced_at": None},
    )
    _set_version(brain, "0.9.9")  # newer, but no authored entry for it
    calls = []
    monkeypatch.setattr("services.auth_service.list_users", lambda: [{"name": "A"}])
    monkeypatch.setattr("services.suggestions_service.notify_user", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(help_service, "get_content", lambda: _content_with("0.3.0"))

    res = wn.announce_if_updated()
    assert res["announced"] is False and res["reason"] == "no-entry"
    assert calls == []
    # baseline is left untouched so it fires once the entry is added
    assert read_json(brain / "_system" / "whats_new_state.json")["announced_version"] == "0.2.0"


def test_banner_within_and_after_window(brain, monkeypatch):
    monkeypatch.setattr(help_service, "get_content", lambda: _content_with("0.3.0"))
    monkeypatch.setattr(settings, "whats_new_days", 5)
    now = datetime.now(timezone.utc)

    write_json(
        brain / "_system" / "whats_new_state.json",
        {"announced_version": "0.3.0", "announced_at": now.isoformat()},
    )
    banner = wn.get_banner()
    assert banner["version"] == "0.3.0"
    assert banner["highlights"] == ["hi 0.3.0"]

    # Past the window → nothing to show.
    old = (now - timedelta(days=10)).isoformat()
    write_json(
        brain / "_system" / "whats_new_state.json",
        {"announced_version": "0.3.0", "announced_at": old},
    )
    assert wn.get_banner()["version"] is None

    # Baseline set but never announced (announced_at None) → no banner.
    write_json(
        brain / "_system" / "whats_new_state.json",
        {"announced_version": "0.3.0", "announced_at": None},
    )
    assert wn.get_banner()["version"] is None


def test_late_version_stamp_announces_on_recheck(brain, monkeypatch):
    """The update.sh race: at boot the stamp still shows the old version (silent),
    then update.sh writes the new one — the scheduler re-check must announce."""
    write_json(
        brain / "_system" / "whats_new_state.json",
        {"announced_version": "0.3.0", "announced_at": None},
    )
    _set_version(brain, "0.3.0")  # boot happens before update.sh stamps
    calls = []
    monkeypatch.setattr("services.auth_service.list_users", lambda: [{"name": "A"}])
    monkeypatch.setattr(
        "services.suggestions_service.notify_user", lambda name, *a, **k: calls.append(name)
    )
    monkeypatch.setattr(help_service, "get_content", lambda: _content_with("0.3.1", "0.3.0"))

    assert wn.announce_if_updated()["announced"] is False  # boot-time: not newer yet

    _set_version(brain, "0.3.1")  # update.sh stamps after health check
    res = wn.announce_if_updated()  # boot+180s one-shot / daily job
    assert res["announced"] is True and calls == ["A"]


def test_release_tag_normalization():
    from services.update_service import _normalize_tag, _version_gt

    assert _normalize_tag("v0.3.1") == "0.3.1"
    assert _normalize_tag("V0.3.0") == "0.3.0"
    # The capital-V bug: unstripped tag parsed as (0,) and broke comparisons
    assert _version_gt(_normalize_tag("V0.3.1"), "0.3.0") is True
