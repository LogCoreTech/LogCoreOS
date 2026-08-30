"""Assets module manifest. See module_registry.py for the ModuleManifest
contract and docs/MEMORY.md's 2026-08-27 entry for the full design.

First of the three largest, most structurally complex remaining modules
(Assets, Contacts, Finance) — deliberately last per the rollout plan, once
the sidecar-share-index pattern (proven by Notes) and the locked-module
pattern (proven by Tasks/Chat/Dashboards) were both already battle-tested.

services/assets_service.py and services/assets_index.py both deliberately
stay core, never moving into this package — more real external consumers
than any prior conversion's own service:
- services/user_deletion_service.py imports both directly and extensively
  (the same four-sharing-capable-stores treatment as assets/finance/
  contacts/notes).
- services/dashboard_blocks/_actions.py (nav_button/status_button),
  _contacts.py (Contacts' own future custom_fields/linked_assets blocks),
  and _collections.py all call assets_service directly.
- routers/contacts.py's link_deal_asset/unlink_deal_asset endpoints call
  assets_service.find_asset() to validate a link.
- module_packages/dashboard/backend/router.py — Dashboards' own already-
  converted router — imports assets_service directly for its Dashboard
  Hero subject resolver (subject_type == "asset"). A sibling module
  package depending on it directly is the strongest possible confirmation
  this has to stay core.
- main.py's _warm_share_index() unconditionally rebuilds assets_index at
  every boot, the same way it does for finance/contacts/notes.
Same "real external consumers keep a service in core" pattern as every
prior conversion, just with more dependents than any before it.

The Collection block (dashboard_blocks/_collections.py, historically kept
separate from _assets.py despite being 100% Assets-data-dependent today —
its own docstring anticipates future generalization to other record types)
folds into this module's own dashboard_block.py alongside the 4 blocks
that were already in _assets.py, and gets module="assets" gating like the
rest — a real, currently-ungated gap closed now rather than left for a
hypothetical future generalization that hasn't happened yet.

The instance-wide n8n automation token (automations_config.py, shared by
both Assets' and Contacts' own automation APIs) stays exactly where it's
always lived — core, unowned by either module. But its only admin-facing
management endpoints (GET/POST token, rotate) used to live INSIDE this
router, gated by nothing but require_admin — meaning uninstalling Assets
(optional, not locked) would have silently taken away the admin's only way
to view/rotate a token Contacts' own automation API still depends on. Found
during this conversion's own research, moved to routers/auth.py's admin
section (permanent core, same precedent as its other admin/*-settings
endpoints) as part of the conversion rather than carried forward silently.

No markdown Brain content exists for Assets at all (assets.json/
templates.json are JSON, attachments are binary files under Assets/files/)
— same structural category as Tasks/Dashboards, not Notes/Chat's
conditional owned_brain_paths gap. "Assets" added to the unconditional
structural skip sets (routers/brain.py's _ALWAYS_SKIP, agent_service.py's
_brain_skip()) for documentation honesty, matching Tasks'/Dashboards' own
precedent — a no-op today since there's no markdown to protect, but honest
about what this module owns."""

from pathlib import Path

from module_registry import ModuleManifest, SearchProviderSpec, search_match


def _get_router():
    from module_packages.assets.backend.router import router

    return router


def _search_assets(query: str, tags: list[str], user: dict, workspace: str) -> list[dict]:
    from services import assets_service

    results = []
    items = assets_service.list_visible(
        user["name"],
        workspace,
        is_admin=user.get("role") == "admin",
        pool_edit=user.get("pool_edit") or [],
        viewer_role=user.get("feature_role") or "",
    )
    for a in items:
        own_tags = a.get("tags") or []
        haystack = " ".join(
            filter(
                None,
                [
                    a.get("name"),
                    a.get("notes"),
                    *[str(v) for v in (a.get("fields") or {}).values()],
                ],
            )
        )
        if search_match(query, tags, haystack, own_tags):
            results.append(
                {
                    "title": a["name"],
                    "snippet": a.get("notes"),
                    "tags": own_tags,
                    "record_id": a["id"],
                }
            )
    return results


def m028_backfill_assets_installed_from_existing_data(brain: Path) -> None:
    """Every instance that existed before this migration shipped had assets
    permanently on — mark it installed so upgrading never silently takes
    the feature away. A genuinely fresh instance has no `_system/features.json`
    yet, so it correctly skips this and starts with assets NOT installed.
    Same existence-guard idiom as journal's m015/calendar's m020/notes' m026."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return

    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return

    mod_store_service.mark_installed("assets", by="migration:m028")


MODULE = ModuleManifest(
    id="assets",
    display_name="Assets",
    description="Track anything you own as flexible, nestable objects built from templates.",
    icon="🗂️",  # matches constants.js's existing nav icon; help_section below keeps its own pre-existing 📦, unrelated/unchanged
    version="1.0.0",
    router_prefix="/api/v1/assets",
    router_tags=["assets"],
    get_router=_get_router,
    owned_brain_paths=["Assets"],
    owned_agent_tools=[
        "list_asset_templates",
        "list_assets",
        "create_asset",
        "update_asset",
        "archive_asset",
        "search_assets",
        "move_asset",
        "delete_asset",
        "create_asset_template",
        "update_asset_template",
    ],
    read_only_agent_tools=["list_asset_templates", "list_assets", "search_assets"],
    admin_agent_tools=["delete_asset", "create_asset_template", "update_asset_template"],
    owned_block_types=[
        "documents",
        "linked_tasks",
        "linked_contact",
        "my_assets_summary",
        "collection",
    ],
    owned_search_providers=[
        SearchProviderSpec(key="assets", label="Assets", resolve=_search_assets),
    ],
    migrations=[
        (
            "assets:m028_backfill_assets_installed_from_existing_data",
            m028_backfill_assets_installed_from_existing_data,
        ),
    ],
    help_section={
        "id": "assets",
        "icon": "📦",
        "title": "Assets",
        "blurb": "Track anything you own — property, vehicles, equipment — as flexible, nestable objects built from templates. Great for organizing and for handing employees limited access.",
        "howto": [
            "Pick a template (an admin sets up the field structure, e.g. a Vehicle or Folder) and create an asset — or start blank if nothing needs to be tracked in structured fields. A blank asset can still have its own custom fields, picked from the same field types templates use (text, number, date, yes/no, dropdown, contact) — no template required.",
            'Built out a blank asset\'s custom fields and want to reuse that structure? Click "Save as template" on it — it becomes a real, reusable template, and the asset itself switches over to using it.',
            "Nest assets under each other (a parcel under a subdivision, equipment under a building) to build a tree.",
            "Attach images or PDFs, add notes, and link related tasks.",
            "Click an asset to read it first; hit ✎ Edit to change it. Share a subtree with a user, your team, or your household.",
            'Give a contributor limited "contribute" access — pick exactly which fields they can change and whether they can add comments, files, or child assets.',
        ],
        "tips": [
            "Comments on an asset are an attributed log — a good way for a crew to leave notes that notify the owner.",
            "Archiving hides an asset without deleting it; hard delete is admin-only and blocked while it still has children.",
        ],
        "modules": ["assets"],
    },
)
