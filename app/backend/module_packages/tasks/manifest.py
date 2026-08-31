"""Tasks module manifest — the first LOCKED (uninstallable=True) module
conversion. See module_registry.py for the ModuleManifest contract and
docs/MEMORY.md's 2026-08-25 entry for the full design, including:
- why services/task_service.py, services/priority_service.py,
  routers/_task_models.py, services/recurring_service.py all stay in core —
  routers/shared.py (Household) and routers/team.py import task_service and
  _task_models directly for their own pool tasks, and agent_service.py/
  suggestions_service.py/dashboard_blocks/{_actions,_assets,_pool}.py all
  depend on task_service directly too, none of them ever converting;
- why the 5 household-pool AI tools (list_shared_tasks, add_shared_task,
  update_shared_task, delete_shared_task, complete_shared_task) stay in
  agent_service.py's core tool set rather than moving here — same reasoning
  as dashboard_blocks/_pool.py's PoolTasksBlock staying core and unowned
  until Household/Team's own future conversion: conceptually Household's
  domain, just implemented via task_service against "_household";
- Goals (/goals) rode this module's own permission gate from 2026-08-25
  (when Tasks itself converted) until 2026-08-28, when it converted into
  its own real module, module_packages/goals/ — its own require_module
  ("goals") gate, own Goals/goals.json store, own manifest. Goals.jsx moved
  out of this package's frontend/ folder to goals/'s own; type=="goal" is
  no longer a valid Task type at all (routers/_task_models.py's Literal
  dropped it, an upgrade migration on goals/'s own manifest converts every
  existing type=="goal" Task into a real Goal record and removes it from
  tasks.json). Tasks gained a new goal_id field (mirrors the existing
  asset_id field exactly) so a Task can still link to a Goal without
  Goals needing to own any part of Tasks' own storage.
"""

from pathlib import Path

from module_registry import ModuleManifest, SearchProviderSpec, search_match


def _get_router():
    from module_packages.tasks.backend.router import router

    return router


def _search_tasks(query: str, tags: list[str], user: dict, workspace: str) -> list[dict]:
    from services import task_service

    results = []
    for t in task_service.list_tasks(user["name"], workspace):
        haystack = " ".join(filter(None, [t.get("title"), t.get("notes"), t.get("category")]))
        if not search_match(query, tags, haystack, t.get("tags") or []):
            continue
        results.append(
            {
                "title": t["title"],
                "snippet": t.get("notes"),
                "tags": t.get("tags") or [],
                "record_id": t["id"],
            }
        )
    return results


def m021_mark_tasks_installed_unconditionally(brain: Path) -> None:
    """Tasks was never optional — unlike every prior conversion's guarded
    upgrade migration (features.json-existence, or a real config file's
    content), this one has no guard at all: a locked (uninstallable=True)
    module must always be installed, on a brand-new instance exactly as much
    as an upgrading one, since active_manifests() (and therefore
    register_routers()) only ever sees it once installed_modules.json says
    so. Every boot — first ever or the thousandth — runs pending migrations
    before register_routers(), so this correctly self-heals on the very
    first boot after this code ships, with no window where /tasks is
    unavailable on a real running instance."""
    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return  # test/alternate brain root — mod_store_service always reads the live one

    mod_store_service.mark_installed("tasks", by="migration:m021")


def m032_migrate_recurrence_to_structured_rule(brain: Path) -> None:
    """Converts every recurring task's plain daily/weekly/monthly recurrence string
    (the pre-2026-08-30 model) into the structured RecurrenceRule shape
    (routers/_task_models.py), deriving the weekday/day-of-month from the task's own
    due_date so its actual next-occurrence behavior doesn't change on upgrade. Covers
    every real user (both workspaces) plus the _household/_team pool stores, same
    iteration pattern as goals/manifest.py's own m031. The isinstance(str) check makes
    this naturally idempotent on top of the migration ledger's own once-only guarantee.
    See services/recurrence_engine.py's legacy_recurrence_to_rule() for the mapping.

    Deliberately skips m031's features.json-existence guard: that guard exists there to
    gate a real fresh-vs-upgrade DECISION (should this optional module auto-install?).
    This migration makes no such decision — tasks is locked/always-installed already
    (m021) — it's a pure data conversion that's a no-op on any store with nothing to
    convert, including a genuinely fresh instance (no users are registered yet at the
    first boot's migration pass, so list_users() is empty and the pool stores are too).
    """
    from services.file_service import brain_path

    if brain != brain_path():
        return  # test/alternate brain root — file_service helpers always read the live one

    from services.auth_service import list_users
    from services.file_service import read_json, tasks_path, write_json
    from services.recurrence_engine import legacy_recurrence_to_rule

    stores: list[tuple[str, str]] = []
    for u in list_users():
        stores.append((u["name"], "personal"))
        stores.append((u["name"], "business"))
    stores.append(("_household", "personal"))
    stores.append(("_team", "personal"))

    for store_user, workspace in stores:
        tpath = tasks_path(store_user, workspace)
        tdata = read_json(tpath, default={"tasks": []})
        changed = False
        for t in tdata.get("tasks", []):
            if t.get("type") == "recurring" and isinstance(t.get("recurrence"), str):
                t["recurrence"] = legacy_recurrence_to_rule(t["recurrence"], t.get("due_date"))
                changed = True
        if changed:
            write_json(tpath, tdata)


MODULE = ModuleManifest(
    id="tasks",
    display_name="Tasks",
    description="Day-to-day to-dos, scored by your life priorities so the most important ones rise to the top.",
    icon="✓",
    version="1.0.0",
    router_prefix="/api/v1/tasks",
    router_tags=["tasks"],
    get_router=_get_router,
    uninstallable=True,
    # Redundant with routers/brain.py's/agent_service.py's own unconditional
    # {"Tasks"} skip (Tasks stores JSON, not markdown — structurally
    # different from every other module's Brain folder, so it was already
    # hidden regardless of any module-disabled toggle before this
    # conversion). Declared here anyway so this manifest is honest about
    # what it owns, and so the generic mechanism stays correct on its own
    # if the always-skip hardcode is ever revisited later.
    owned_brain_paths=["Tasks"],
    owned_agent_tools=[
        "list_tasks",
        "add_task",
        "update_task",
        "delete_task",
        "get_top3_tasks",
        "get_scored_tasks",
        "get_task_history",
        "create_tasks",
        "get_week_snapshot",
    ],
    read_only_agent_tools=[
        "list_tasks",
        "get_top3_tasks",
        "get_scored_tasks",
        "get_task_history",
        "get_week_snapshot",
    ],
    owned_block_types=["top3_tasks", "due_today", "streaks", "single_task"],
    owned_search_providers=[
        SearchProviderSpec(key="tasks", label="Tasks", resolve=_search_tasks),
    ],
    migrations=[
        (
            "tasks:m021_mark_tasks_installed_unconditionally",
            m021_mark_tasks_installed_unconditionally,
        ),
        (
            "tasks:m032_migrate_recurrence_to_structured_rule",
            m032_migrate_recurrence_to_structured_rule,
        ),
    ],
    help_section={
        "id": "tasks",
        "icon": "✅",
        "title": "Tasks",
        "blurb": "Tasks are your day-to-day to-dos. LogCore scores them by your life priorities so the most important ones rise to the top automatically.",
        "howto": [
            'Click "+ New Task", give it a title, and pick a category and priority (High/Medium/Low).',
            "Add a due date and time if it matters — overdue and due-today tasks score highest, and a set time shows right next to the date on the card.",
            'Set Type to "Recurring" for repeating tasks, then pick the pattern: choose Daily/Weekly/Monthly/Yearly and an "Every N" count (every 2 weeks, every 3 days, etc.), then, for Weekly, tap which weekdays it repeats on, or for Monthly/Yearly, choose either a fixed day of the month (or "Last day of month") or "On the Nth weekday" for a pattern like "the 2nd Tuesday." Completing it on schedule builds a streak.',
            'Use the "Sort by" control above the list to switch between Priority score (default — ranks every task against every other one, regardless of category), Date/Time, and Alphabetical; your choice is remembered.',
            "Check a task off to complete it. Non-recurring done tasks move to History during the nightly tidy-up.",
            "Tasks assigned to you from a shared Household or Team pool show up here with a 🏠 badge.",
            "Add tags to group tasks beyond category — click a tag anywhere to filter the list down to just that tag.",
            "Click any task's card to open its full detail — recurring tasks show a real calendar of which days were completed or missed. Edit from there if you need to change something.",
        ],
        "tips": [
            "Your Dashboard shows the top 3 tasks to focus on right now — a filtered view of this list.",
            "Reorder your category priorities in Profile; it directly changes which tasks surface first.",
            'You can also ask the AI in Chat to "add three tasks for the move" and approve them in one step.',
            'Tags are shared with Goals — tag something "urgent" in either place and it means the same thing in both, and you can link a recurring task to a goal to feed it real completion-rate data.',
            "A recurring task's repeat pattern is locked in once created — delete and recreate it if the schedule genuinely needs to change, rather than trying to edit it in place.",
        ],
        "modules": ["tasks"],
    },
)
