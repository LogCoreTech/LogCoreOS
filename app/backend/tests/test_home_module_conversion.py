"""Integration tests for home's actual conversion into module_packages/
(increment 2 of the Mod Store rollout) — not ha_service's own client logic
(untested even before this conversion, see docs/TESTING.md's Coverage Gaps),
but the surrounding machinery: the m016 upgrade migration (deliberately keyed
on ha_config.json's own existence+completeness, not a blanket "every
pre-existing instance had it" assumption like journal's m015), and a full
install/uninstall/reinstall round-trip through the real Mod Store service
with home as the actual target module."""

from migrations.runner import run_pending
from services import mod_store_service
from services.file_service import write_json


def test_m016_marks_home_installed_when_ha_was_already_configured(brain):
    """An existing instance that had already connected Home Assistant (a
    real url+token saved) had the feature effectively on — upgrading must
    not silently disconnect it."""
    write_json(brain / "_system" / "ha_config.json", {"url": "http://ha.local:8123", "token": "abc123"})

    run_pending(brain)

    assert mod_store_service.is_installed("home")


def test_m016_noop_on_fresh_install(brain):
    """No ha_config.json at all means this Brain never connected Home
    Assistant — it should start with home NOT installed, matching the
    actual goal of slimming the default install."""
    assert not (brain / "_system" / "ha_config.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("home")


def test_m016_noop_when_ha_config_file_exists_but_incomplete(brain):
    """A file that exists but never actually got a real url+token (e.g. an
    admin opened the form and saved a blank/partial one) doesn't count as
    "was using this feature" — home stays uninstalled."""
    write_json(brain / "_system" / "ha_config.json", {"url": "", "token": ""})

    run_pending(brain)

    assert not mod_store_service.is_installed("home")


def test_install_uninstall_reinstall_round_trip_preserves_favourites(brain):
    """The real end-to-end guarantee: uninstalling home never touches its
    data, and reinstalling picks it back up immediately."""
    from services import ha_service

    ha_service.save_favourites("dana", ["light.living_room", "switch.porch"])

    mod_store_service.mark_installed("home", by="tester")
    assert mod_store_service.is_installed("home")

    mod_store_service.mark_uninstalled("home", by="tester")
    assert not mod_store_service.is_installed("home")
    # data untouched even while "uninstalled"
    assert ha_service.get_favourites("dana") == ["light.living_room", "switch.porch"]

    mod_store_service.mark_installed("home", by="tester")
    assert mod_store_service.is_installed("home")
    assert ha_service.get_favourites("dana") == ["light.living_room", "switch.porch"]
