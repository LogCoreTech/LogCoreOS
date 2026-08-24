"""Journal module manifest. See module_registry.py for the ModuleManifest
contract and docs/MEMORY.md's 2026-08-24 entry for the full design."""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.journal.backend.router import router

    return router


def m015_backfill_journal_installed_from_existing_data(brain: Path) -> None:
    """Every instance that existed before this migration shipped had journal
    permanently on — mark it installed so upgrading never silently takes the
    feature away. A genuinely fresh instance has no `_system/features.json`
    yet (created during setup, before any migration runs), so it correctly
    skips this and starts with journal NOT installed — the actual goal
    (slimming the default install), not a side effect. Same existence-guard
    idiom migrations/runner.py already uses twice (m007, m008)."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return  # fresh install — journal correctly starts uninstalled

    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return  # test/alternate brain root — mod_store_service always reads the live one

    mod_store_service.mark_installed("journal", by="migration:m015")


def _ensure_journal_folder(user_name: str) -> None:
    from services.file_service import ws_path

    folder = ws_path(user_name, "personal") / "Journal"
    folder.mkdir(parents=True, exist_ok=True)


def _on_install(brain: Path) -> None:
    """Backfill a Journal/ folder for every existing user who doesn't already
    have one — replaces the old unconditional _template/Journal/ copy."""
    from services.file_service import brain_path

    if brain != brain_path():
        return
    users_dir = brain / "USERS"
    if not users_dir.exists():
        return
    for user_dir in users_dir.iterdir():
        if user_dir.is_dir() and not user_dir.name.startswith("_"):
            _ensure_journal_folder(user_dir.name)


def _on_new_user(brain: Path, user_name: str) -> None:
    """Called by routers/setup.py for every currently-active module when a
    new user is provisioned — the other half of _on_install's backfill, so
    a signup that happens weeks after journal was installed still gets a
    Journal/ folder, not just users who existed at install time."""
    _ensure_journal_folder(user_name)


MODULE = ModuleManifest(
    id="journal",
    display_name="Journal",
    description="A private daily journal — one Markdown entry per day.",
    icon="📖",  # matches constants.js's existing nav icon; help_section below keeps its own (📔, pre-existing)
    version="1.0.0",
    router_prefix="/api/v1/journal",
    router_tags=["journal"],
    get_router=_get_router,
    owned_brain_paths=["Journal"],
    owned_agent_tools=["read_journal_entry", "write_journal_entry", "list_journal_entries"],
    read_only_agent_tools=["read_journal_entry", "list_journal_entries"],
    owned_block_types=["journal_entry"],
    migrations=[("journal:m015_backfill_journal_installed_from_existing_data", m015_backfill_journal_installed_from_existing_data)],
    on_install=_on_install,
    on_new_user=_on_new_user,
    help_section={
        "id": "journal",
        "icon": "📔",
        "title": "Journal",
        "blurb": "A private daily journal — one Markdown entry per day, stored by date in your Brain.",
        "howto": [
            "Pick a date (defaults to today) and write your entry in Markdown.",
            "Entries auto-save; use the History button to jump back to a previous day.",
            "Your AI can read journal entries when you ask it to reflect on patterns or summarize a period.",
        ],
        "tips": ["Journal is personal-workspace only."],
        "modules": ["journal"],
    },
)
