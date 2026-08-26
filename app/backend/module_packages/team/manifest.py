"""Team module manifest. See household/manifest.py for the fuller design
writeup this mirrors — services/task_service.py/events_service.py/
routers/_task_models.py/_event_models.py all stay core for the same
reason (this router imports them directly), and the old shared
`pool_tasks` dashboard block's business-workspace half lives here as
`team_tasks` (household's own m023 migration carries the rename forward
for both halves in one pass — team declares no migration of its own for
that). No agent tools exist for Team today (unlike Household's shared-task
management tools) — this is a real, pre-existing asymmetry between the two
pools, not something invented or fixed as part of this conversion."""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.team.backend.router import router

    return router


def m024_backfill_team_installed_from_existing_data(brain: Path) -> None:
    """Every instance that existed before this migration shipped had team
    permanently on — mark it installed so upgrading never silently takes
    the feature away. A genuinely fresh instance has no
    `_system/features.json` yet, so it correctly skips this and starts
    with team NOT installed. Same existence-guard idiom as household's own
    m022."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return

    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return

    mod_store_service.mark_installed("team", by="migration:m024")


MODULE = ModuleManifest(
    id="team",
    display_name="Team",
    description="A shared pool of tasks and events for your business team.",
    icon="🧑‍🤝‍🧑",
    version="1.0.0",
    router_prefix="/api/v1/team",
    router_tags=["team"],
    get_router=_get_router,
    owned_brain_paths=[],
    owned_agent_tools=[],
    owned_block_types=["team_tasks"],
    migrations=[
        (
            "team:m024_backfill_team_installed_from_existing_data",
            m024_backfill_team_installed_from_existing_data,
        ),
    ],
    help_section={
        "id": "team",
        "icon": "🧑‍🤝‍🧑",
        "title": "Team",
        "blurb": "The business-workspace equivalent of Household: a shared task and event pool for your team, kept structurally separate from any personal/family data.",
        "howto": [
            "Switch to the business workspace, then open Team to see shared tasks and events.",
            "Members read and complete; adding/editing/assigning needs admin or a \"Can manage\" grant.",
            "Assign work to a teammate and it appears on their Tasks and Calendar.",
        ],
        "tips": [
            "Team lives only in the business workspace. Personal/Household data can never leak into it.",
        ],
        "modules": ["team"],
    },
)
