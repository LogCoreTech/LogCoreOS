"""Tests for homes/manifest.py's m033_install_homes migration.

Real bug found live 2026-09-20: m033 originally ran unconditionally
(copied from Goals' own migration shape, which deliberately joined the
fresh-install default baseline — an explicit owner decision Homes was
never part of), silently turning Homes on for every instance the moment
it shipped. Fixed to match the OTHER, more common pattern instead —
Assets'/Contacts'/Finance's own backfill migrations (see
tests/test_assets_module_conversion.py's identical two tests) — a
genuinely fresh instance (no `_system/features.json`) starts with Homes
NOT installed, opt-in via Mod Store."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from migrations.runner import run_pending
from services import mod_store_service


def test_m033_marks_homes_installed_on_upgrade(brain):
    (brain / "_system" / "features.json").write_text('{"profile": "personal", "roles": {}}')

    run_pending(brain)

    assert mod_store_service.is_installed("homes")


def test_m033_noop_on_fresh_install(brain):
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("homes")
