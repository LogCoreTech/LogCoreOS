"""Goals module manifest. See module_registry.py for the ModuleManifest
contract and docs/MEMORY.md's 2026-08-28 entry for the full design.

Not a mechanical conversion like the prior 13 modules (there was no
routers/goals.py or services/goals_service.py to move) — Goals used to be
100% Task records with type=="goal", filtered client-side, riding on Tasks'
own permission gate (App.jsx's /goals route used moduleId="tasks"; no
require_module("goals") existed anywhere). This is a genuinely new module,
scoped through direct interview after the 13-module rollout finished, built
on real requirements: subgoals nested inside goals (unbounded depth, mirrors
Assets' own parent_id/collect_subtree_ids pattern), linked Tasks (a new
goal_id field on Task, mirrors the existing asset_id field), a metric picker
that can pull a goal's completion percentage from live data in another
module, and a "ME" view of root-level goals as life goals.

services/module_packages/goals/backend/service.py deliberately stays fully
inside this package (unlike task_service.py/assets_service.py/etc., which
stay core because of real external consumers) — nothing outside this
package needs Goals data directly. Goals doesn't get the per-user
share-handshake pattern Assets/Finance/Contacts/Notes use (no shared_with/
contributors on an individual goal — only pool visibility), so
services/user_deletion_service.py needs no Goals-specific handling: a
user's personal goals are deleted with the rest of their Brain folder, same
as their Tasks already are.

Pool (household/team) goals are served from THIS module's own router, not
from household's/team's — the same "a single owning module serves personal
+ pool" shape Finance/Contacts/Assets/Notes already use, not the older
per-pool-router shape Tasks/Calendar predate. This ties pool-goal
availability to Goals' OWN install state. household_goals/team_goals
dashboard BLOCKS are the one exception — those live in household's/team's
own dashboard_block.py, gated module="household"/module="team" (not
"goals"), mirroring household_tasks/team_tasks' own established precedent
exactly (gate on pool membership, not on the underlying data-owning
module).

The metric-provider mechanism (ModuleManifest.owned_metric_providers,
module_registry.metric_providers()) is generic, extensible infrastructure
added alongside this conversion — Goals itself contains ZERO
module-specific metric logic; it just discovers and lists whatever's
registered. v1 ships three providers: the built-in tree/task rollup (native
to Goals, not through the registry at all), "manual" (a logged-history
number the user enters by hand, also native), and two real
registry-discovered ones declared on THEIR OWN owning modules' manifests —
Finance's budget-category percent (module_packages/finance/manifest.py) and
Contacts' number-type custom field (module_packages/contacts/manifest.py).
Assets/Journal/Calendar/Home Assistant/Automations providers are deliberate
fast-follow, not built in this pass — the mechanism supports them being
added later exactly like this without touching Goals' own code at all.

type=="goal" is no longer a valid Task type at all —
routers/_task_models.py's Literal dropped it, task_service.py's
cleanup_done_goals() (the old "Clear completed" mechanism) was removed
outright since Goals now owns that concept over real Goal records instead,
and priority_service.py's/recurring_service.py's own now-dead
goal-exclusion filters were simplified away."""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.goals.backend.router import router

    return router


def m031_migrate_goals(brain: Path) -> None:
    """Guarded the same way as every other optional module's own upgrade
    migration (features.json existence = "this instance existed before
    Goals became a real module"). Does two things in one pass: marks goals
    installed, and converts every existing type=="goal" Task (across every
    real user, both workspaces, and both pool pseudo-users) into a real
    Goal record, removing it from tasks.json. A genuinely fresh instance has
    no features.json yet, so it correctly skips both and starts with goals
    NOT installed — same "slimming the default install" goal every optional
    module's own migration already follows."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return

    from services.file_service import brain_path

    if brain != brain_path():
        return  # test/alternate brain root — file_service helpers always read the live one

    from services import mod_store_service

    mod_store_service.mark_installed("goals", by="migration:m031")

    from module_packages.goals.backend.service import goal_from_legacy_task, write_json_direct
    from services.auth_service import list_users
    from services.file_service import goals_path, read_json, tasks_path, write_json

    stores: list[tuple[str, str]] = []
    for u in list_users():
        stores.append((u["name"], "personal"))
        stores.append((u["name"], "business"))
    stores.append(("_household", "personal"))
    stores.append(("_team", "personal"))

    for store_user, workspace in stores:
        tpath = tasks_path(store_user, workspace)
        tdata = read_json(tpath, default={"tasks": []})
        legacy = [t for t in tdata.get("tasks", []) if t.get("type") == "goal"]
        if not legacy:
            continue

        gdata = read_json(goals_path(store_user, workspace), default={"goals": []})
        gdata["goals"] = list(gdata.get("goals", [])) + [goal_from_legacy_task(t) for t in legacy]
        write_json_direct(store_user, workspace, gdata)

        legacy_ids = {t["id"] for t in legacy}
        tdata["tasks"] = [t for t in tdata["tasks"] if t["id"] not in legacy_ids]
        write_json(tpath, tdata)


MODULE = ModuleManifest(
    id="goals",
    display_name="Goals",
    description="Bigger outcomes broken into subgoals and linked tasks, with an optional live metric to track real progress.",
    icon="🎯",
    version="1.0.0",
    router_prefix="/api/v1/goals",
    router_tags=["goals"],
    get_router=_get_router,
    owned_brain_paths=["Goals"],
    owned_agent_tools=[
        "list_goals",
        "get_goal",
        "create_goal",
        "update_goal",
        "delete_goal",
        "link_task_to_goal",
        "unlink_task_from_goal",
    ],
    read_only_agent_tools=["list_goals", "get_goal"],
    owned_block_types=["goals_progress"],
    migrations=[
        ("goals:m031_migrate_goals", m031_migrate_goals),
    ],
    help_section={
        "id": "goals",
        "icon": "🎯",
        "title": "Goals",
        "blurb": "Bigger outcomes than a daily task — broken into subgoals and linked tasks, with an optional live metric so progress updates itself instead of needing a manual checkmark.",
        "howto": [
            "Create a goal, then add subgoals underneath it — a subgoal can have its own subgoals, as deep as you need.",
            "Link an existing task to a goal, or create a new one straight from the goal's own page — linked tasks show up right alongside its subgoals.",
            "You can also link an already-existing goal in as a subgoal instead of creating a new one — it moves there from wherever it was before.",
            "\"ME\" shows all of your own personal goals; if you're in a household or team, a second tab shows that pool's shared goals.",
            "Set a metric on a goal — pull live data from Finance (a budget category's percent), a number field on one of your Contacts, your own weight, or just log a number by hand (pages read, anything you track over time).",
            "Metrics can count up to a target (savings, pages read) or down to one (weight, debt) — pick the direction when you set the target.",
            "A goal with no metric and no subgoals/tasks underneath it is a plain manual checkbox, same as before.",
            "A goal with subgoals or linked tasks (and no metric of its own) shows their combined progress automatically — a linked recurring task contributes its own real completion rate, not just whether it happens to be checked off today.",
            "Deleting a goal with subgoals asks whether to delete them too or just move them up a level, and separately whether to delete its linked tasks or just unlink them.",
            "Ask the AI to break a goal into tasks — the tasks it creates link back to the goal automatically.",
            "Add tags to a goal or task to group them beyond category — click a tag anywhere to filter the list down to just that tag.",
        ],
        "tips": [
            "A goal with both a target value and a due date shows whether you're on pace to hit it.",
            "You'll get a notification the moment a goal's progress crosses 100%.",
            "Tags are shared between Goals and Tasks — tag something \"urgent\" in either place and it means the same thing in both.",
            "The pool tab only shows up if your household or team is set up — everyone in it sees the same shared goals by default.",
            "Each linked recurring task has its own \"Counts toward this goal's progress\" checkbox — turn it off to track its completion rate for your own reference without it moving the goal's overall percentage; a newly linked recurring task starts with it off until you turn it on.",
        ],
        "modules": ["goals"],
    },
)
