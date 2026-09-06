"""Calendar module manifest. Deliberately narrow move, same shape as
Automations: id/directory/routes/every internal name stay "calendar" — no
rename requested. See module_registry.py for the ModuleManifest contract
and docs/MEMORY.md's 2026-08-25 entry for the full design, including why
services/events_service.py and routers/_event_models.py both stay in
core — routers/shared.py (Household) and routers/team.py import them
directly for their own pool calendars, confirmed independent of this
module's own install state (require_module("household")/("team"), never
require_module("calendar"))."""

from pathlib import Path

from module_registry import ModuleManifest, SearchProviderSpec, search_match


def _get_router():
    from module_packages.calendar.backend.router import router

    return router


def _search_calendar(query: str, tags: list[str], user: dict, workspace: str) -> list[dict]:
    from services import events_service

    results = []
    for e in events_service.list_events(user["name"], workspace):
        own_tags = e.get("tags") or []
        haystack = " ".join(filter(None, [e.get("title"), e.get("notes")]))
        if search_match(query, tags, haystack, own_tags):
            results.append(
                {
                    "title": e["title"],
                    "snippet": e.get("notes"),
                    "tags": own_tags,
                    "record_id": e["id"],
                }
            )
    return results


def m020_backfill_calendar_installed_from_existing_data(brain: Path) -> None:
    """Every instance that existed before this migration shipped had
    calendar permanently on — mark it installed so upgrading never silently
    takes the feature away. Journal, Calendar, Notes, and Goals joined the
    fresh-install default baseline (2026-09-04 UX Polish Batch, item #12) —
    unlike the other optional modules, this migration no longer skips on a
    genuinely fresh instance (no `_system/features.json` yet); it runs
    unconditionally, once, on any instance, fresh or upgrading. See
    docs/MEMORY.md's 2026-09-04 entry for the full rationale."""
    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return  # test/alternate brain root — mod_store_service always reads the live one

    mod_store_service.mark_installed("calendar", by="migration:m020")


def _on_new_user(brain: Path, user_name: str) -> None:
    """2026-09-04 UX Polish Batch item #11 — one seeded example event per new
    user, prefixed "Example: " so it's obviously safe to delete."""
    from services.seed_data_service import seed_calendar_event

    seed_calendar_event(user_name)


MODULE = ModuleManifest(
    id="calendar",
    display_name="Calendar",
    description="A month view of your world: events you create plus any tasks that have a due date, all on one grid.",
    icon="📅",  # matches constants.js's existing nav icon
    version="1.0.0",
    router_prefix="/api/v1/calendar",
    router_tags=["calendar"],
    get_router=_get_router,
    on_new_user=_on_new_user,
    owned_brain_paths=["Calendar"],
    owned_agent_tools=[],  # no AI chat tools exist for calendar today — not adding new ones as part of converting what's already there
    read_only_agent_tools=[],
    owned_block_types=["upcoming_events", "single_event"],
    owned_trash_types=["event"],
    owned_search_providers=[
        SearchProviderSpec(key="events", label="Calendar", resolve=_search_calendar),
    ],
    migrations=[
        (
            "calendar:m020_backfill_calendar_installed_from_existing_data",
            m020_backfill_calendar_installed_from_existing_data,
        ),
    ],
    help_section={
        "id": "calendar",
        "icon": "📅",
        "title": "Calendar",
        "blurb": "A month view of your world: events you create plus any tasks that have a due date, all on one grid.",
        "howto": [
            'Click a day to see its detail, or click "+ New Event" to add one with a title, date, colour, and notes.',
            "Tasks with due dates appear as pills on their day automatically — no need to add them twice.",
            "Toggle the 🏠 / 🧑‍🤝‍🧑 pill to overlay shared Household (personal) or Team (business) events and tasks.",
            'Use the "Add to Household" toggle in the event editor to move a personal event into the shared pool.',
        ],
        "tips": [
            "The calendar follows your active workspace — personal and business each have their own events.",
        ],
        "modules": ["calendar"],
    },
)
