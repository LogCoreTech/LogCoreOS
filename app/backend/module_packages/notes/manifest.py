"""Notes module manifest. See module_registry.py for the ModuleManifest
contract and docs/MEMORY.md's 2026-08-26 entry for the full design.

The first conversion to genuinely test the sidecar-share-index sharing
pattern (Notes/_shares.json + notes_index.py's derived owner->workspace
cache) — the direct precedent Assets/Contacts/Finance will need for their
own future conversions. services/notes_service.py and
services/notes_index.py both deliberately stay in core, never moving into
this package: services/user_deletion_service.py imports both directly
(alongside the equivalent assets/contacts/finance pairs, treated as one
uniform quartet of sharing-capable stores during account deletion), and
main.py's _warm_share_index() unconditionally rebuilds notes_index at every
boot the same way it does for assets/finance/contacts. Same "real external
consumers keep a service in core" pattern as task_service.py/events_service.py.

Three real, pre-existing enforcement gaps this conversion closes (found
during upfront research, not introduced by it):
1. All 7 note AI tools lived in agent_service.py's unfiltered static
   _USER_TOOLS list, so a user with the Notes module disabled could still
   list/read/create/update/delete/move their notes via chat — module-owned
   tools are the only ones _get_tools() actually filters by disabled_modules.
   Moving them into owned_agent_tools closes this for free.
2. No owned_brain_paths entry meant a disabled user's own Notes/ folder was
   fully readable via the Brain browser and the AI's own
   list_brain_files/read_brain_file/search_brain tools regardless of module
   state — closed by owned_brain_paths=["Notes"].
3. The note_embed dashboard block had no module= gate at all (the exact
   pool_tasks-before-Household/Team situation) — closed by adding module="notes"
   to its BlockSpec.
"""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.notes.backend.router import router

    return router


def m026_backfill_notes_installed_from_existing_data(brain: Path) -> None:
    """Every instance that existed before this migration shipped had notes
    permanently on — mark it installed so upgrading never silently takes the
    feature away. A genuinely fresh instance has no `_system/features.json`
    yet, so it correctly skips this and starts with notes NOT installed.
    Same existence-guard idiom as journal's m015/automations' m019/
    calendar's m020/household's m022."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return

    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return

    mod_store_service.mark_installed("notes", by="migration:m026")


MODULE = ModuleManifest(
    id="notes",
    display_name="Notes",
    description="Markdown notes organized in folders, shareable with people or a household/team pool.",
    icon="📝",
    version="1.0.0",
    router_prefix="/api/v1/notes",
    router_tags=["notes"],
    get_router=_get_router,
    owned_brain_paths=["Notes"],
    owned_agent_tools=[
        "list_notes",
        "read_note",
        "create_note",
        "update_note",
        "delete_note",
        "move_note",
        "create_note_folder",
    ],
    read_only_agent_tools=["list_notes", "read_note"],
    owned_block_types=["note_embed"],
    migrations=[
        (
            "notes:m026_backfill_notes_installed_from_existing_data",
            m026_backfill_notes_installed_from_existing_data,
        ),
    ],
    help_section={
        "id": "notes",
        "icon": "📝",
        "title": "Notes",
        "blurb": "Markdown notes organized in folders. They save themselves as you type and stay plain, portable files in your Brain.",
        "howto": [
            "Create a note or folder from the sidebar; click a note to edit it in Markdown.",
            "There's no Save button — notes auto-save about a second and a half after you stop typing.",
            "Drag a note onto a folder to move it, or use the \"Move to folder\" menu.",
            "Share a note or a whole folder with another user or a pool from the Share menu.",
            "Archive a note or folder from its ··· menu to tuck it out of the way without deleting it; toggle \"Show archived\" to see archived items again.",
        ],
        "tips": [
            "Sharing a folder cascades to everything inside it.",
            "Shared notes stay plain Markdown — the sharing info is kept separately so your files remain portable.",
            "Archiving a folder cascades to everything inside it too, same as sharing.",
            "Admins can rename, move, share, archive, and delete notes shared into the household/team pool, same as any other shared module.",
        ],
        "modules": ["notes"],
    },
)
