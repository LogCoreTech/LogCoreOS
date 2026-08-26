"""Household module manifest. See module_registry.py for the ModuleManifest
contract and docs/MEMORY.md's 2026-08-25 entry for the full design,
including why services/task_service.py, services/events_service.py,
routers/_task_models.py, and routers/_event_models.py all stay in core
(this router imports them directly, same as it always has) and why the old
shared `pool_tasks` dashboard block split into `household_tasks` (here)
and `team_tasks` (module_packages/team/) — a single BlockSpec can only
carry one `module=` string, so a block serving both pools couldn't be
gated to either module individually once both became real, discoverable
modules.

Router prefix deliberately stays `/api/v1/shared` (not `/api/v1/household`)
— that's the historical mount point (routers/shared.py, tags=["shared"]),
unrelated to the module id, and the owner asked for no rename this round,
matching Calendar's/Tasks' own no-rename conversions."""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.household.backend.router import router

    return router


def m022_backfill_household_installed_from_existing_data(brain: Path) -> None:
    """Every instance that existed before this migration shipped had
    household permanently on — mark it installed so upgrading never
    silently takes the feature away. A genuinely fresh instance has no
    `_system/features.json` yet, so it correctly skips this and starts
    with household NOT installed. Same existence-guard idiom as journal's
    m015/automations' m019/calendar's m020."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return

    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return

    mod_store_service.mark_installed("household", by="migration:m022")


def m023_rename_pool_tasks_block_type(brain: Path) -> None:
    """Carry-forward for the block type split pool_tasks -> household_tasks
    (personal-workspace dashboards) / team_tasks (business-workspace
    dashboards) — without this, any dashboard that already had the old
    block added would break the moment this code deploys: the old type
    string stops matching anything BLOCK_REGISTRY/dashboard_blocks
    REGISTRY know about, and the block renders as unresolvable. Runs once
    for both modules together (household owns this migration; team's own
    manifest carries no equivalent) since it's one read/write pass per
    dashboard either way — splitting it into two migrations would mean
    reading and writing the same files twice for no benefit.

    Deliberately raw read_json/write_json throughout, never
    dashboards_service.update_dashboard() — same reasoning as
    home_assistant's own m018 block-type-rename migration, which this
    mirrors almost exactly, just workspace-aware instead of a flat 1:1
    rename."""
    from services import dashboards_service
    from services.auth_service import list_users
    from services.file_service import (
        brain_path,
        dashboard_templates_path,
        dashboards_path,
        global_dashboard_templates_path,
        read_json,
        write_json,
    )

    if brain != brain_path():
        return  # test/alternate brain root — these path helpers always read the live one

    OLD = "pool_tasks"
    NEW_BY_WORKSPACE = {"personal": "household_tasks", "business": "team_tasks"}

    def _rename(blocks, new_type):
        changed = False
        out = []
        for b in blocks or []:
            if b.get("type") == OLD:
                b = {**b, "type": new_type}
                changed = True
            out.append(b)
        return out, changed

    # Every real user + pool dashboard, both workspaces — the new type is
    # picked per-dashboard by that dashboard's OWN workspace, not a flat
    # rename, since the same old type meant different things in each.
    for store_user, workspace in dashboards_service._all_stores():
        new_type = NEW_BY_WORKSPACE.get(workspace)
        if new_type is None:
            continue
        path = dashboards_path(store_user, workspace)
        data = read_json(path, default={"dashboards": []})
        file_changed = False
        for d in data.get("dashboards", []):
            new_blocks, changed = _rename(d.get("blocks"), new_type)
            if changed:
                d["blocks"] = new_blocks
                file_changed = True
        if file_changed:
            write_json(path, data)

    # Every real user's own templates — templates aren't workspace-scoped
    # the way dashboards are, so a pool_tasks block in a personal template
    # becomes household_tasks; there's no business-workspace equivalent
    # store to consider here (templates belong to the user, not a
    # workspace).
    for u in list_users():
        path = dashboard_templates_path(u["name"])
        data = read_json(path, default={"templates": []})
        file_changed = False
        for t in data.get("templates", []):
            new_blocks, changed = _rename(t.get("blocks"), "household_tasks")
            if changed:
                t["blocks"] = new_blocks
                file_changed = True
        if file_changed:
            write_json(path, data)

    # Admin-curated global templates — same reasoning as above.
    global_path = global_dashboard_templates_path()
    data = read_json(global_path, default={"templates": []})
    file_changed = False
    for t in data.get("templates", []):
        new_blocks, changed = _rename(t.get("blocks"), "household_tasks")
        if changed:
            t["blocks"] = new_blocks
            file_changed = True
    if file_changed:
        write_json(global_path, data)


MODULE = ModuleManifest(
    id="household",
    display_name="Household",
    description="A shared pool of tasks and events for your family or household.",
    icon="🏠",
    version="1.0.0",
    router_prefix="/api/v1/shared",
    router_tags=["shared"],
    get_router=_get_router,
    owned_brain_paths=[],
    owned_agent_tools=[
        "complete_shared_task",
        "list_household_members",
        "list_shared_tasks",
        "add_shared_task",
        "update_shared_task",
        "delete_shared_task",
    ],
    read_only_agent_tools=["list_household_members", "list_shared_tasks"],
    # These 4 stay hidden from non-admin callers' tool lists entirely (not
    # just execution-blocked) — complete_shared_task is deliberately absent
    # here, since any household member may call it, just gated to their own
    # assigned tasks (or admin) inside execute() itself.
    admin_agent_tools=[
        "list_household_members",
        "list_shared_tasks",
        "add_shared_task",
        "update_shared_task",
        "delete_shared_task",
    ],
    owned_block_types=["household_tasks"],
    migrations=[
        (
            "household:m022_backfill_household_installed_from_existing_data",
            m022_backfill_household_installed_from_existing_data,
        ),
        (
            "household:m023_rename_pool_tasks_block_type",
            m023_rename_pool_tasks_block_type,
        ),
    ],
    help_section={
        "id": "household",
        "icon": "🏡",
        "title": "Household",
        "blurb": "A shared pool of tasks and events for your family or household. Everyone with the module can see it; managing it can be granted per person.",
        "howto": [
            "Open Household to see all shared tasks and events in one place.",
            "Any member can complete or un-complete shared tasks.",
            "Adding, editing, deleting, or assigning items requires pool-management rights — an admin grants \"Can manage\" per user.",
            "Assign a task to a member and it shows up on their personal Tasks and Calendar with a 🏠 badge.",
        ],
        "tips": [
            "Household is personal-workspace only and completely separate from the business Team pool — data never crosses between them.",
        ],
        "modules": ["household"],
    },
)
