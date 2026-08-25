"""Automations module manifest (display name "n8n Automation" — id,
directory, routes, and every internal name deliberately left as
"automations" per the owner's explicit instruction; only the forward-facing
name changed, unlike Home Assistant's full internal rename). See
module_registry.py for the ModuleManifest contract and docs/MEMORY.md's
2026-08-25 entry for the full design, including why n8n_service.py and
automations_config.py both stay in core rather than moving here, and why
the (never-enforcing) "automations_business" role-editor toggle was
removed rather than converted."""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.automations.backend.router import router

    return router


def m019_backfill_automations_installed_from_existing_data(brain: Path) -> None:
    """Every instance that existed before this migration shipped had
    Automations permanently on — mark it installed so upgrading never
    silently takes the feature away. A genuinely fresh instance has no
    `_system/features.json` yet (created during setup, before any migration
    runs), so it correctly skips this and starts with automations NOT
    installed — the actual goal (slimming the default install). Same
    existence-guard idiom journal's m015 uses (Automations, like journal,
    was always-on before this system existed — unlike Home Assistant's
    m016, which had to key on real ha_config.json content instead, since
    Home Assistant was already opt-in)."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return  # fresh install — automations correctly starts uninstalled

    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return  # test/alternate brain root — mod_store_service always reads the live one

    mod_store_service.mark_installed("automations", by="migration:m019")


MODULE = ModuleManifest(
    id="automations",
    display_name="n8n Automation",
    description="Run background workflows with n8n, and review what they surface in a built-in Inbox.",
    icon="⚙️",  # matches constants.js's existing nav icon
    version="1.0.0",
    router_prefix="/api/v1/automations",
    router_tags=["automations"],
    get_router=_get_router,
    owned_brain_paths=["Automations"],
    owned_agent_tools=[],  # no AI chat tools exist for automations today — not adding new ones as part of converting what's already there
    read_only_agent_tools=[],
    owned_block_types=["workflow_status", "inbox_summary"],
    migrations=[
        (
            "automations:m019_backfill_automations_installed_from_existing_data",
            m019_backfill_automations_installed_from_existing_data,
        ),
    ],
    help_section={
        "id": "automations",
        "icon": "⚙️",
        "title": "n8n Automation",
        "blurb": "Run background workflows with n8n, and review what they surface in a built-in Inbox.",
        "howto": [
            "Under Workflows, import an n8n workflow JSON, then run it, activate it, or view its logs.",
            "Switch to the Inbox to review items your workflows post (e.g. leads to qualify).",
            "Act on each item — Interested / Pass / Offer Made / Closed — and it's recorded with your name.",
            "Named inboxes route items from specific workflows and notify the right people.",
        ],
        "tips": [
            "Business workflows live in the shared team scope; personal ones are yours alone.",
            "The bundled n8n only runs when you actually have workflows, keeping things lightweight.",
        ],
        "modules": ["automations"],
    },
)
