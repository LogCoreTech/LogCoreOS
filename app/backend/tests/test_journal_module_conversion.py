"""Integration tests for journal's actual conversion into module_packages/
(increment 1 of the Mod Store rollout) — not journal_service's own CRUD logic
(covered by module_packages/journal/tests/test_journal_service.py), but the
surrounding machinery: the m015 upgrade migration, the on_install/on_new_user
backfill hooks, and a full install/uninstall/reinstall round-trip through the
real Mod Store endpoints with journal as the actual target module."""

from migrations.runner import run_pending
from module_packages.journal.manifest import MODULE as journal_manifest
from services import mod_store_service
from services.file_service import ws_path


def test_m015_marks_journal_installed_on_upgrade(brain):
    """An existing instance (has _system/features.json from a prior setup)
    had journal permanently on before this system existed — upgrading must
    not silently take it away."""
    (brain / "_system" / "features.json").write_text('{"profile": "personal", "roles": {}}')

    run_pending(brain)

    assert mod_store_service.is_installed("journal")


def test_m015_noop_on_fresh_install(brain):
    """No _system/features.json yet means this Brain never went through the
    always-on-journal era — it should start with journal NOT installed,
    matching the actual goal of slimming the default install."""
    # brain fixture creates _system/ but not features.json — genuinely fresh
    assert not (brain / "_system" / "features.json").exists()

    run_pending(brain)

    assert not mod_store_service.is_installed("journal")


def test_on_install_backfills_journal_folder_for_existing_users(brain):
    alice_dir = brain / "USERS" / "alice"
    bob_dir = brain / "USERS" / "bob"
    alice_dir.mkdir(parents=True)
    bob_dir.mkdir(parents=True)
    # bob already has one (from before journal was ever made a module) — must not error
    (bob_dir / "Journal").mkdir()

    journal_manifest.on_install(brain)

    assert (alice_dir / "Journal").is_dir()
    assert (bob_dir / "Journal").is_dir()


def test_on_install_ignores_pseudo_users(brain):
    """Pool pseudo-users (_household, _team) shouldn't get a Journal folder —
    journal is personal, never shared/pooled."""
    (brain / "USERS" / "_household").mkdir(parents=True)

    journal_manifest.on_install(brain)

    assert not (brain / "USERS" / "_household" / "Journal").exists()


def test_on_new_user_creates_journal_folder(brain):
    journal_manifest.on_new_user(brain, "carol")
    assert ws_path("carol", "personal").joinpath("Journal").is_dir()


def test_install_uninstall_reinstall_round_trip_preserves_data(brain):
    """The real end-to-end guarantee: uninstalling journal never touches its
    data, and reinstalling picks it back up immediately."""
    from module_packages.journal.backend import service as journal_service

    journal_service.upsert_entry("dana", "2026-01-01", "a real entry")

    mod_store_service.mark_installed("journal", by="tester")
    assert mod_store_service.is_installed("journal")

    mod_store_service.mark_uninstalled("journal", by="tester")
    assert not mod_store_service.is_installed("journal")
    # data untouched even while "uninstalled"
    assert journal_service.get_entry("dana", "2026-01-01")["content"] == "a real entry"

    mod_store_service.mark_installed("journal", by="tester")
    assert mod_store_service.is_installed("journal")
    assert journal_service.get_entry("dana", "2026-01-01")["content"] == "a real entry"
