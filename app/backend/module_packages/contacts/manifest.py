"""Contacts module manifest. See module_registry.py for the ModuleManifest
contract and docs/MEMORY.md's 2026-08-28 entry for the full design.

Second of the three largest, most structurally complex remaining modules
(Assets, Contacts, Finance) — deliberately last per the rollout plan, once
the sidecar-share-index pattern (proven by Notes) and the locked-module
pattern (proven by Tasks/Chat/Dashboards) were both already battle-tested.

services/contacts_service.py and services/contacts_index.py both
deliberately stay core, never moving into this package — same "real
external consumers keep a service in core" pattern as every prior
conversion, with more dependents than most:
- services/user_deletion_service.py imports both directly and extensively
  (the same four-sharing-capable-stores treatment as assets/finance/
  contacts/notes).
- module_packages/dashboard/backend/router.py — Dashboards' own already-
  converted router — imports contacts_service directly for its Dashboard
  Hero subject resolver (subject_type == "contact"). A sibling module
  package depending on it directly is the strongest possible confirmation
  this has to stay core, the same evidence that kept assets_service core.
- module_packages/chat/backend/router.py imports it (lazily) for the AI
  system-prompt's own profile context (get_self_contact/format_profile_text).
- services/agent_service.py's core get_profile/update_profile tools call it
  directly — Profile is a generic concept independent of Contacts' module
  state, so these two tools stay core rather than moving into this
  package's own agent_tools.py (see that file's own docstring).
- services/profile_service.py, dashboard_blocks/_actions.py,
  dashboard_blocks/_custom_fields.py, finance_invoice_service.py,
  finance_service.py all call it too.
- routers/auth.py (registration self-contact linking), routers/setup.py
  (initial setup), migrations/runner.py, scheduler.py
  (run_followup_reminders), and main.py's _warm_share_index() (which
  unconditionally rebuilds contacts_index at every boot, same as
  assets/finance/notes) all depend on it directly.
- routers/auth.py's DeletionDecision.module Literal already lists
  "contacts" alongside "assets"/"finance"/"notes" — a converted module's
  service staying reachable from this same core enum is expected, not a
  sign it should have moved (notes_service.py already proves this).

Two dashboard blocks (linked_deals, contacts_list) are exclusively
Contacts' own and move into this package's dashboard_block.py, gated
module="contacts" — as does linked_assets (a contact's reverse lookup of
assets referencing it via a `contact`-type field, distinct from Assets'
own `linked_contact` block, which is the asset->contact forward
direction). A FOURTH contact-adjacent block, custom_fields, does NOT move
here — it genuinely reads from either contacts_service OR assets_service
depending on which config field is set (record_ref_fields declares both
contact_id and asset_id), the same "spans more than one module, owned by
none" shape as dashboard_blocks/_actions.py's nav_button/status_button.
It stays in core dashboard_blocks/_custom_fields.py (split out of the old
_contacts.py as part of this conversion), ungated by module=, rather than
becoming exclusively Contacts-owned by virtue of which package file it
happened to live in before this move.

Two admin-gated-but-not-module-gated endpoints were found during this
conversion's own research, matching the shape (not the fix) of Assets'
own automation-token finding — each judged independently rather than
reflexively "fixed" the same way:
- PUT /contacts/fields (author custom-field definitions) had require_admin
  but no require_module("contacts"), unlike its own GET sibling — a real,
  narrow inconsistency (an admin whose own account has contacts disabled
  could still edit Contacts' own field schema). Fixed by adding
  require_module("contacts") alongside require_admin, matching GET.
- GET /contacts/available-for-linking (the "link an existing contact to
  a new user account" picker) is DELIBERATELY left ungated on
  require_module, on top of require_admin — same reasoning as
  GET/PATCH /contacts/me: self-contact linking is account-creation
  infrastructure that must keep working regardless of whether Contacts is
  disabled for the acting admin or uninstalled instance-wide, exactly like
  a self-contact itself always resolves. Not a gap, a deliberate match to
  an existing precedent.

No markdown Brain content exists for Contacts at all (contacts/
interactions/deals/pipeline.json are JSON, photos are binary files under
Contacts/photos/) — same structural category as Tasks/Dashboards/Assets,
not Notes/Chat's conditional owned_brain_paths gap. "Contacts" added to
the unconditional structural skip sets (routers/brain.py's _ALWAYS_SKIP,
agent_service.py's _brain_skip()) for documentation honesty, matching
Assets' own precedent — a no-op today since there's no markdown to
protect (list_brain_files/search_brain are hardcoded to *.md only
regardless), but honest about what this module owns.

The 6 AI agent tools (list_contacts/get_contact/create_contact/
update_contact/log_interaction/create_deal) lived unfiltered in
agent_service.py's static _USER_TOOLS list before this — the same
enforcement-gap shape Chat's/Notes'/Dashboards'/Assets' own conversions
each found and closed in their turn. No admin-only Contacts tool exists
(unlike Assets' 3), so this manifest declares no admin_agent_tools."""

from pathlib import Path

from module_registry import MetricProviderSpec, ModuleManifest, SearchProviderSpec, search_match

# Shared by both metric providers below — same shape as Goals' own "manual"
# provider's config_schema entries (module_packages/goals/backend/router.py)
# so the picker UI behaves identically regardless of which provider it's
# configuring.
_DIRECTION_FIELD = {
    "key": "direction",
    "label": "Direction",
    "kind": "select",
    "options": [
        {"value": "increase", "label": "Increase to target (e.g. pages read, savings)"},
        {"value": "decrease", "label": "Decrease to target (e.g. weight, debt)"},
    ],
}
# Weight gets its OWN direction field with "decrease" listed first — the
# frontend picker (MetricPicker.jsx) pre-selects options[0] whenever the
# config doesn't have an explicit value yet, and _resolve_weight's own
# default is "decrease" (weight LOSS being the more common goal framing).
# Reusing _DIRECTION_FIELD as-is here would show "Increase" pre-selected in
# the UI while the backend was actually already computing "decrease" behind
# the scenes the moment target_value was set without touching this field —
# a real visual/effective mismatch caught before shipping, not after.
_WEIGHT_DIRECTION_FIELD = {
    **_DIRECTION_FIELD,
    "options": [
        {"value": "decrease", "label": "Decrease to target (e.g. weight loss)"},
        {"value": "increase", "label": "Increase to target (e.g. bulking)"},
    ],
}
_START_VALUE_FIELD = {
    "key": "start_value",
    "label": 'Starting value (required for "decrease")',
    "kind": "number",
    "optional": True,
}


def _resolve_number_field(config: dict, user: dict, workspace: str) -> dict:
    """Goals metric provider (2026-08-28) — a number-type custom field's
    current value vs. a target_value, defaulting to the caller's own
    self-contact when no contact_id is given (this is what "track a health
    metric on my own profile" turned out to mean — Contacts already has the
    number-type custom field this needs, no new field system required).
    Never raises, same contract as every MetricProviderSpec.resolve."""
    from module_registry import directional_pct
    from services import contacts_service

    contact_id = config.get("contact_id")
    viewer = user.get("name", "")
    if contact_id:
        found = contacts_service.find_contact(
            viewer, user.get("role", "member"), user.get("role") == "admin", workspace, contact_id
        )
        if found is None:
            return {"current": 0, "target": None, "pct": 0}
        _store_user, contact, _access = found
    else:
        contact = contacts_service.get_self_contact(viewer)
        if contact is None:
            return {"current": 0, "target": None, "pct": 0}

    field_key = config.get("field_key")
    target = config.get("target_value")
    current = (contact.get("custom") or {}).get(field_key)
    if not isinstance(current, (int, float)):
        return {"current": 0, "target": target, "pct": 0}
    pct = directional_pct(
        current, target, config.get("direction", "increase"), config.get("start_value")
    )
    return {"current": current, "target": target, "pct": pct}


def _resolve_weight(config: dict, user: dict, workspace: str) -> dict:
    """Goals metric provider (2026-08-29, owner ask: "the metrics for users
    personal contact data needs to be accessible for their personal goals...
    weight") — weight_kg is a built-in, always-private Contact field (see
    services/contacts_service.py's _PRIVATE_SHORT_FIELDS), NOT part of the
    admin-defined custom-fields system _resolve_number_field reads — hence
    its own dedicated provider rather than folding it into that one. Always
    the caller's own self-contact (no contact_id override — the field is
    private by design, only ever readable by its own owner). Defaults
    direction to "decrease" (weight LOSS is the more common goal framing)
    but the config exposes the same direction toggle as the manual metric
    so a bulking goal isn't stuck with backwards math."""
    from module_registry import directional_pct
    from services import contacts_service

    contact = contacts_service.get_self_contact(user.get("name", ""))
    if contact is None:
        return {"current": 0, "target": None, "pct": 0}

    current = contact.get("weight_kg")
    target = config.get("target_value")
    if not isinstance(current, (int, float)):
        return {"current": 0, "target": target, "pct": 0}
    pct = directional_pct(
        current, target, config.get("direction", "decrease"), config.get("start_value")
    )
    return {"current": current, "target": target, "pct": pct}


def _get_router():
    from module_packages.contacts.backend.router import router

    return router


def _search_contacts(query: str, tags: list[str], user: dict, workspace: str) -> list[dict]:
    """Deliberately its own haystack, not a reuse of contacts_service's own
    search_contacts() (the AI tool's function, name+emails+tags only) — a
    different consumer with a narrower, already-shipped contract; widening
    it here would risk an unrelated behavior change to the AI tool."""
    from services import contacts_service

    results = []
    contacts = contacts_service.list_visible_contacts(
        user["name"], user.get("feature_role", "member"), user.get("role") == "admin", workspace
    )
    for c in contacts:
        own_tags = c.get("tags") or []
        haystack = " ".join(
            filter(
                None,
                [
                    c.get("name"),
                    c.get("notes"),
                    c.get("address"),
                    " ".join(c.get("core_values") or []),
                ],
            )
        )
        if search_match(query, tags, haystack, own_tags):
            results.append(
                {
                    "title": c.get("name") or "(unnamed)",
                    "snippet": c.get("notes"),
                    "tags": own_tags,
                    "record_id": c["id"],
                }
            )
    return results


def m029_backfill_contacts_installed_from_existing_data(brain: Path) -> None:
    """Every instance that existed before this migration shipped had contacts
    permanently on — mark it installed so upgrading never silently takes
    the feature away. A genuinely fresh instance has no `_system/features.json`
    yet, so it correctly skips this and starts with contacts NOT installed.
    Same existence-guard idiom as journal's m015/calendar's m020/notes' m026/
    assets' m028."""
    features_file = brain / "_system" / "features.json"
    if not features_file.exists():
        return

    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return

    mod_store_service.mark_installed("contacts", by="migration:m029")


MODULE = ModuleManifest(
    id="contacts",
    display_name="Contacts",
    description="Your address book and light CRM — contacts, interactions, deals, and your own Profile.",
    icon="👥",  # matches constants.js's existing nav icon and help_section's own pre-existing icon
    version="1.0.0",
    router_prefix="/api/v1/contacts",
    router_tags=["contacts"],
    get_router=_get_router,
    owned_brain_paths=["Contacts"],
    owned_agent_tools=[
        "list_contacts",
        "get_contact",
        "create_contact",
        "update_contact",
        "log_interaction",
        "create_deal",
    ],
    read_only_agent_tools=["list_contacts", "get_contact"],
    owned_block_types=["linked_deals", "contacts_list", "linked_assets"],
    owned_metric_providers=[
        MetricProviderSpec(
            key="number_field",
            label="Contacts: Number Field",
            config_schema=[
                {
                    "key": "contact_id",
                    "label": "Contact (leave blank for your own profile)",
                    "kind": "contact",
                    "optional": True,
                },
                {"key": "field_key", "label": "Field", "kind": "contactNumberField"},
                _DIRECTION_FIELD,
                _START_VALUE_FIELD,
                {"key": "target_value", "label": "Target value", "kind": "number"},
            ],
            resolve=_resolve_number_field,
        ),
        MetricProviderSpec(
            key="weight",
            label="Contacts: My Weight",
            config_schema=[
                _WEIGHT_DIRECTION_FIELD,
                _START_VALUE_FIELD,
                {"key": "target_value", "label": "Target weight", "kind": "number"},
            ],
            resolve=_resolve_weight,
        ),
    ],
    owned_search_providers=[
        SearchProviderSpec(key="contacts", label="Contacts", resolve=_search_contacts),
    ],
    migrations=[
        (
            "contacts:m029_backfill_contacts_installed_from_existing_data",
            m029_backfill_contacts_installed_from_existing_data,
        ),
    ],
    help_section={
        "id": "contacts",
        "icon": "👥",
        "title": "Contacts (CRM)",
        "blurb": "Your address book and light CRM. The Contact is the canonical person or company that Finance payees and invoice clients link back to — and every user's own Profile is now a Contact too.",
        "howto": [
            "Add a contact with emails, phones (with country code and extension), tags, and any admin-defined custom fields — it's shared with your household or team by default, with a \"keep this personal\" option if you'd rather it stay just yours.",
            "Any contact can also be flipped to show up in your other workspace too, from the editor — it's still one real record, not a copy, so an edit from either tab always changes the same contact.",
            'Your own Profile lives here as a self-contact, pinned to the top of your Contacts list labeled "ME" — visible to your whole household and team from either workspace, and it opens as a full page since there\'s a lot more on it than a typical contact.',
            "Upload a photo for any contact — it replaces the default icon at the top of the card.",
            'Build a work history under Career — add a role, then "Archive this role & start a new one" when it ends, keeping past roles on record like a resume. You can also add a past role directly with its own start and end dates, or edit one later — past roles list with the most recent one first.',
            "Filter the list to just people or just companies.",
            "The list sorts alphabetically by name — jump straight to a letter with the A-Z strip beside it.",
            "Tag a contact as a company and its editor switches to company fields — Locations (one or more addresses) and Hours (open/close per day) instead of personal fields like gender or career.",
            "Log interactions (calls, emails, meetings, notes) to keep a timeline for each contact.",
            "Track opportunities on the deals pipeline (Lead → Contacted → … → Won/Lost).",
            "Set a follow-up date on an interaction or deal to get reminded.",
            "Link two contacts as affiliated (family, a company and its people, etc.) — the link shows on both contacts' cards.",
            'Share contacts like assets and finance — "contribute" lets someone log interactions and advance deals without editing the core record.',
            "Delete a contact from its edit screen — your own contacts anytime, a shared household/team contact only if you're an admin.",
            "Convert a personal contact into a shared household/team contact from its edit screen — or convert several at once from the → Household/Team button in the Contacts page toolbar, which only shows up when you have contacts eligible to convert.",
            "Add Core Values as individual pills, one at a time, instead of typing them all into one field.",
            'On your own profile, each of the Personal, Address, Career, Family, Values & Principles, and Priorities sections has a "Hide from others" toggle right next to its heading — turn one on and your household/team stops seeing that section, while you still see everything yourself.',
        ],
        "tips": [
            "Link a payee or an invoice client to a contact to see all their spend/receive activity in one place.",
            "Won deals offer a shortcut to create an invoice in Finance.",
            "Health, finances, and AI-preference fields on your own profile are always private — never visible to anyone you share your contact with, no matter what access level you grant.",
            "Nobody but you can ever be granted edit access to your own contact, even if you share it — others can only get read or contribute access.",
            "A green or red dot on a household/team member's own contact shows whether they're currently online — click their photo to see exactly how long ago they were last seen.",
            "The section-hiding toggles on your own profile are only ever settable by you — nobody with access to your contact, even at edit level, can turn one on or off.",
        ],
        "modules": ["contacts"],
    },
)
