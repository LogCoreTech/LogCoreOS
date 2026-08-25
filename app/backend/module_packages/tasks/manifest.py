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
- why Goals (/goals) is NOT part of this conversion's manifest — it's a
  purely frontend nav-only pseudo-module (no require_module("goals") exists
  anywhere in the backend; App.jsx gates /goals on moduleId="tasks", the
  same real permission as /tasks) that was never manifest-driven to begin
  with. Goals.jsx itself DOES move into this package's frontend/ folder, but
  its CORE_MODULES nav entry and its own content/help.json section both stay
  exactly where they already were — no new multi-page manifest mechanism
  needed, since the existing 1-manifest-1-primary-route shape was never
  actually violated by Goals sharing Tasks' permission gate.
"""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.tasks.backend.router import router

    return router


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
    owned_block_types=["top3_tasks", "due_today", "streaks", "goals_progress", "single_task"],
    migrations=[
        (
            "tasks:m021_mark_tasks_installed_unconditionally",
            m021_mark_tasks_installed_unconditionally,
        ),
    ],
    help_section={
        "id": "tasks",
        "icon": "✅",
        "title": "Tasks",
        "blurb": "Tasks are your day-to-day to-dos. LogCore scores them by your life priorities so the most important ones rise to the top automatically.",
        "howto": [
            "Click \"+ New Task\", give it a title, and pick a category and priority (High/Medium/Low).",
            "Add a due date and time if it matters — overdue and due-today tasks score highest, and a set time shows right next to the date on the card.",
            "Set Type to \"Recurring\" for repeating tasks; completing them on schedule builds a streak.",
            "Use the \"Sort by\" control above the list to switch between Priority score (default — ranks every task against every other one, regardless of category), Date/Time, and Alphabetical; your choice is remembered.",
            "Check a task off to complete it. Non-recurring done tasks move to History during the nightly tidy-up.",
            "Tasks assigned to you from a shared Household or Team pool show up here with a 🏠 badge.",
        ],
        "tips": [
            "Your Dashboard shows the top 3 tasks to focus on right now — a filtered view of this list.",
            "Reorder your category priorities in Profile; it directly changes which tasks surface first.",
            "You can also ask the AI in Chat to \"add three tasks for the move\" and approve them in one step.",
        ],
        "modules": ["tasks"],
    },
)
