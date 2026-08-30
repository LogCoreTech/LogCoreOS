"""Dashboards module manifest — the third LOCKED (uninstallable=True) module,
after Tasks and Chat. See module_registry.py for the ModuleManifest contract
and docs/MEMORY.md's 2026-08-27 entry for the full design.

Keeps the existing `dashboard` (singular) module id and directory — no
rename, matching Automations'/Calendar's own "no rename requested"
precedent. The alternative (`dashboards`, plural, matching this package's
own name) would be a real id rename, the same weight as Home Assistant's
`home`->`home_assistant` move, needing its own carry-forward migration for
every already-stored `disabled_modules`/role entry — not warranted here.

services/dashboards_service.py, services/dashboard_templates_service.py,
services/dashboard_index.py, and the entire services/dashboard_blocks/
package all deliberately stay core, never moving into this package:
- migrations/runner.py's own core migrations (m010 seed-home, m011/m012
  grid-unit rescales) call dashboards_service directly, and migrations run
  BEFORE discover_manifests()/register_routers() in boot order — a module
  package's own service literally cannot be imported that early.
- module_packages/household/manifest.py's m023 and
  module_packages/home_assistant/manifest.py's m018 (both block-type-rename
  carry-forwards) also import dashboards_service._all_stores() directly.
- main.py's _warm_share_index() unconditionally rebuilds dashboard_index at
  every boot, the same way it does for assets/finance/contacts/notes.
- dashboard_blocks/ (registry.py, render.py, every block resolver) has zero
  router/endpoint of its own — it's plumbing every module's own blocks run
  on top of, the same category as module_registry.py itself, confirmed by
  the original rollout plan's own closing note and by direct grep (zero
  FastAPI imports anywhere in that package).
Same "real external consumers keep a service in core" pattern as
task_service.py/events_service.py — just with migrations/runner.py itself
as a dependent this time, which is a stronger, structural reason than any
prior conversion had.

Dashboards owns zero block types of its own (it's the container, never an
entry in dashboard_blocks/registry.py's REGISTRY) — no backend/dashboard_block.py.

owned_brain_paths=["Dashboards"] is declared for the same reason Tasks'
own manifest declares owned_brain_paths=["Tasks"] even though "Dashboards"
is ALSO added to the unconditional structural skip sets (routers/brain.py's
_ALWAYS_SKIP, agent_service.py's _brain_skip()) — Dashboards data is JSON,
not markdown, so it's always skipped regardless of module state; the
conditional declaration is redundant but honest about what this module
owns, matching Tasks' own precedent exactly.

App.jsx's root route (`<Route path="/" element={<Dashboard />} />`) stays
hardcoded and UNWRAPPED by ModuleRoute — this is new ground no prior
conversion needed: Dashboards is the only module whose manifest.js `to`
is `/`, and MODULE_PACKAGES.map()'s generic route-generation loop is
filtered to skip any package claiming `/` (App.jsx's own comment explains
why — a user with `dashboard` in their disabled set would otherwise hit a
self-targeting redirect loop at the app's own home page)."""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.dashboard.backend.router import router

    return router


def m027_mark_dashboard_installed_unconditionally(brain: Path) -> None:
    """Dashboards was never optional — same no-existence-guard shape as
    tasks' own m021 and chat's own m025, since a locked (uninstallable=True)
    module must always be installed, on a brand-new instance exactly as
    much as an upgrading one."""
    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return  # test/alternate brain root — mod_store_service always reads the live one

    mod_store_service.mark_installed("dashboard", by="migration:m027")


MODULE = ModuleManifest(
    id="dashboard",
    display_name="Dashboards",
    description="Build-it-yourself dashboards — a freeform grid of blocks pulling live data from almost any module.",
    icon="⊞",  # matches constants.js's existing nav icon; help_section below keeps its own pre-existing 🏠, unrelated/unchanged
    version="1.0.0",
    router_prefix="/api/v1/dashboards",
    router_tags=["dashboards"],
    get_router=_get_router,
    uninstallable=True,
    owned_brain_paths=["Dashboards"],
    owned_agent_tools=[
        "list_dashboards",
        "get_dashboard",
        "list_dashboard_templates",
        "get_dashboard_block_catalog",
        "create_dashboard",
        "add_dashboard_block",
        "update_dashboard_block",
        "remove_dashboard_block",
        "create_dashboard_template",
        "update_dashboard_template",
    ],
    read_only_agent_tools=[
        "list_dashboards",
        "get_dashboard",
        "list_dashboard_templates",
        "get_dashboard_block_catalog",
    ],
    owned_block_types=[],
    migrations=[
        (
            "dashboard:m027_mark_dashboard_installed_unconditionally",
            m027_mark_dashboard_installed_unconditionally,
        ),
    ],
    help_section={
        "id": "dashboard",
        "icon": "🏠",
        "title": "Dashboard",
        "blurb": "Your home screen — now build-it-yourself. Create as many dashboards as you want, each a freeform grid of blocks pulling live data from almost any module: tasks, streaks, Home Assistant, Finance, Contacts, Assets, Notes, Calendar, n8n Automation, and more.",
        "howto": [
            "Click the dashboard name at the top to switch between your dashboards — grouped by template if you use them — or create a new one.",
            "Click \"Edit Dashboard\" to drag/resize blocks, add new ones, or remove existing ones — works the same way on desktop and mobile, and each remembers its own arrangement, so a dashboard can be laid out differently on your phone than on your laptop. On a touchscreen, press and hold a block for a moment before it starts moving — a quick swipe scrolls the page as normal instead. Removing a block asks you to confirm first. A block's ✎/✕ edit controls only show up while you're editing.",
            'Every block has its own card background and name/icon header shown by default — click "✎" on a block to turn either one off individually, for a cleaner, more minimal look on blocks that don\'t need the label or the card outline.',
            'Click "+ Add Block" and use the search box to find one quickly, or browse the full catalog grouped into live data, record-linked, actions, and freeform (text/links/headings). Record-linked blocks (Single Task, Contact\'s Deals, Finance Book Report, etc.) let you search for and pick the exact task, contact, asset, event, book, note, or workflow — you never need to know or type an internal ID. The Documents/Files block shows real image previews and lets you click any file to open it.',
            "The Collection block shows a whole list — or a board grouped by status — of records at once from one asset template, optionally narrowed to just the ones linked to the dashboard's own contact. Pick which fields show, and pick one of the template's own status-style fields to get a one-click status control on every item, right from the dashboard. A Count-only layout is also available for a simple \"how many\" tile.",
            'When creating a new dashboard, you can start blank or pick a template to build from a reusable block set instantly — templates are entirely optional. Some templates ask you to pick a contact or asset first (their "subject"); any block set up to use "this dashboard\'s own contact/asset" then shows that record\'s data. A dashboard made from a template keeps its block set in sync with the template automatically, but its own layout stays yours to rearrange — use "Detach from template" (in ⚙ Settings) for full independent control over its blocks too.',
            'Two Action blocks render as a small standalone button with nothing else around it, so you can fit several in a small space: "Navigate To…" jumps to any page, a specific section within Finance/n8n Automation/Settings, a specific record, or a specific dashboard; "Status/Archive Action" marks a task done/pending/skipped, updates a contact\'s gender or marital status, or archives/unarchives an asset or sets one of its own fields, with one click. Every option in both is picked from a real list, never typed — including the button\'s own label and its color, if you want something more specific than the default.',
            'While editing, click "⚙ Settings" to rename the dashboard, change its icon, share it, set it as your default, or delete it — all in one place, or — if you have both a personal and business workspace — flip on "Also show in my [other workspace] workspace" so this one dashboard shows up in both instead of just the one it was created in.',
            "Sharing (inside ⚙ Settings) lets you share a dashboard with another person or your household/team pool at read, contribute, or edit access.",
            "As the owner, you can turn on \"Share underlying data\" (also inside ⚙ Settings) so people you've shared with see the same live data you do, even things they normally couldn't access on their own — off by default, and they never see more than you can see.",
            "New here? The Getting Started card walks you through first steps and hides once you're set up.",
            "A dashboard made from a template that picked a contact or asset shows a banner with its photo/icon and name right at the top, so it's always clear who or what the dashboard is about.",
        ],
        "tips": [
            'Your first dashboard, "Home," was created automatically from your old fixed dashboard widgets — fully editable and deletable like any other, as long as you have at least one other dashboard.',
            "A dashboard with only one block left can't be deleted while it's your only dashboard in that workspace — LogCore always keeps you at least one landing page.",
            'Picked the wrong record for a block? Click its "✎" button while editing to change what it points to, without deleting and re-adding the block.',
            'Manage templates from the "Templates" button next to "+ New Dashboard." Admins can build global templates for everyone; anyone can also build and share their own personal ones — just like Asset Templates.',
            'Made a dashboard from a template? ⚙ Settings lets you change which contact/asset it\'s about ("Change subject") at any time.',
            "To resize a block, drag the small orange corner mark in its bottom-right corner while editing (desktop only).",
            "A dashboard you leave open picks up changes made elsewhere (a task created on another device, for example) on its own every so often — no manual reload needed.",
            "Reopening the Dashboard module takes you back to whichever dashboard you had open last, as long as it's been less than 30 minutes — otherwise it falls back to your default.",
        ],
        "modules": ["dashboard"],
    },
)
