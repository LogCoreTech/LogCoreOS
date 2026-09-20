"""Homes module manifest — see module_registry.py for the ModuleManifest
contract. Manages houses (rented or owned) as their own records, then pulls
in everything else tagged with a house's own auto-generated tag from every
other active module via search_service.search() — this module owns almost
no data of its own beyond the house record itself; Tasks/Notes/Calendar/
Finance/Assets/Contacts already own the real content.

id="homes" (plural), not "home" — that id belonged to Home Assistant before
its 2026-08-24 same-day rename to "home_assistant"; reusing it here would
read as a confusable leftover. "household" is a separate, unrelated concept
(the family/pool grouping), not houses-as-property.

Pool (household/team) homes are served from THIS module's own router, not
household's/team's — the same "a single owning module serves personal +
pool" shape Goals/Finance/Contacts/Assets/Notes already use, tying pool-home
availability to Homes' OWN install state. Access model deliberately mirrors
Goals' simpler tier (explicit `pool: bool` + pool_edit-or-admin check, no
per-user shared_with/contributors handshake) rather than Finance's heavier
peer-invite sharing — a house is realistically a whole-household concern,
not something invited person-by-person.

The tag a house generates on creation is a real, ordinary member of
services/tags_service.py's per-store vocabulary — nothing tag-related is
new; Homes just calls register_tags() once at creation time so the tag is
selectable elsewhere immediately, same as Goals already does."""

from pathlib import Path

from module_registry import ModuleManifest, SearchProviderSpec, search_match


def _get_router():
    from module_packages.homes.backend.router import router

    return router


def _search_homes(query: str, tags: list[str], user: dict, workspace: str) -> list[dict]:
    """Makes a home findable by name/address via the app-wide search bar
    itself — the reverse direction of Homes' own aggregation (which finds
    OTHER modules' records tagged with a home's tag). Deliberately v1-
    deferred when Homes first shipped (2026-09-18), built 2026-09-20.

    `tags=[]` on every result: a home has no arbitrary user-assigned tags of
    its own (only the single frozen `tag` string other records reference),
    so a tag-only search (as Homes' own GET /{id}/items performs) must never
    match a home here — the whole point is this provider is a plain-text
    lookup, not another way to browse-by-tag. Without this, a home would
    self-referentially list itself as one of its own "tagged items" during
    Homes' own aggregation, since search() fans out across every active
    provider including this one.

    Pool visibility mirrors router.py's own `_pool_user`/`_pool_installed`
    logic, duplicated (not imported) — every module's manifest.py keeps this
    kind of tiny pool-mapping check local to itself rather than sharing it
    across files, same as household's/team's own search functions do."""
    from module_packages.homes.backend import service as homes_service
    from services import mod_store_service

    pool_id = "household" if workspace == "personal" else "team"
    homes = homes_service.list_homes(user["name"], workspace)
    if mod_store_service.is_installed(pool_id):
        pool_user = "_household" if workspace == "personal" else "_team"
        homes = homes + homes_service.list_homes(pool_user, "personal")

    results = []
    for h in homes:
        haystack = " ".join(filter(None, [h.get("name"), h.get("address"), h.get("notes")]))
        if search_match(query, tags, haystack, []):
            results.append(
                {
                    "title": h["name"],
                    "snippet": h.get("address") or h.get("notes"),
                    "tags": [],
                    "record_id": h["id"],
                }
            )
    return results


def m033_install_homes(brain: Path) -> None:
    from services.file_service import brain_path

    if brain != brain_path():
        return  # test/alternate brain root — file_service helpers always read the live one

    from services import mod_store_service

    mod_store_service.mark_installed("homes", by="migration:m033")


MODULE = ModuleManifest(
    id="homes",
    display_name="Homes",
    description="Manage your rented or owned homes — tasks, notes, and money for each one pulled together in one place.",
    icon="🏘️",
    version="1.0.0",
    router_prefix="/api/v1/homes",
    router_tags=["homes"],
    get_router=_get_router,
    owned_brain_paths=["Homes"],
    owned_agent_tools=[
        "list_homes",
        "get_home",
        "create_home",
        "update_home",
        "delete_home",
    ],
    read_only_agent_tools=["list_homes", "get_home"],
    owned_trash_types=["home"],
    owned_search_providers=[
        SearchProviderSpec(key="homes", label="Homes", resolve=_search_homes),
    ],
    migrations=[
        ("homes:m033_install_homes", m033_install_homes),
    ],
    help_section={
        "id": "homes",
        "icon": "🏘️",
        "title": "Homes",
        "blurb": "One page per house — rented or owned — pulling together every task, note, event, and expense you've tagged as belonging to it.",
        "howto": [
            "Create a home and pick Rent or Own — each has its own relevant fields (lease dates and rent for a rental, purchase details and mortgage payment for one you own).",
            "Every home gets its own tag the moment you create it, shown on its Overview tab — apply that tag to a task, note, event, transaction, asset, or contact anywhere else in the app and it shows up here automatically.",
            "Link a landlord or lender straight to an existing Contact so their info stays in one place.",
            "If you're in a household or team, an admin (or anyone granted pool management) can create a home that everyone shares instead of one just for themselves.",
            "Deleting a home moves it to Trash like everything else — restorable for 30 days. Tagged items elsewhere are never touched by deleting the home itself.",
        ],
        "tips": [
            "The Overview tab shows a quick preview across every tagged item; Tasks, Notes, Money, and Events each get their own tab for the full list.",
            "Renaming a home never changes its tag, so nothing you've already tagged gets orphaned.",
        ],
        "modules": ["homes"],
    },
)
