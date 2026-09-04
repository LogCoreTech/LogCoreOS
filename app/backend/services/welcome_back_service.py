"""Welcome-back popup (item #25, 2026-09-04 UX Polish Batch): a middle-screen
popup shown after a configurable away-threshold, optionally with an AI
summary of what changed while the user was gone.

"Away" is derived from presence_service's existing seen_at ping (Layout.jsx
already pings this every 30s while a page is visible) rather than a new
per-request write — see docs/MEMORY.md's 2026-09-04 entry for why a
synchronous per-request last_active write was rejected (lock-contention risk
at that call frequency).

Data gathering for the AI summary goes through each module's own
sharing-aware service functions (list_visible_notes, list_tasks, etc.), the
same functions the real HTTP endpoints use — never a raw file read — per the
standing rule in docs/MEMORY.md's 2026-08-14 entry. Journal is never
shareable anywhere in this app; this only ever reads the viewer's OWN
journal, matching that boundary.

v1 scope: Tasks, Journal, Notes, Calendar events. Finance/Contacts/Assets are
a deliberate fast-follow, not included here yet — each needs its own
book/store enumeration step (Finance transactions are per-book) that would
have made this pass significantly larger without a correspondingly higher
first-cut payoff.
"""

from datetime import datetime, timedelta, timezone

from services import presence_service

_DEFAULT_THRESHOLD_DAYS = 7


def should_show(user: dict) -> bool:
    """True if this user has been away at least their configured threshold
    (default 7 days) since their last real presence ping."""
    seen_at = presence_service.last_seen_iso(user["name"])
    if not seen_at:
        return False  # never pinged before — not a "welcome back", a first visit
    try:
        seen = datetime.fromisoformat(seen_at)
    except ValueError:
        return False
    threshold_days = user.get("welcome_back_threshold_days") or _DEFAULT_THRESHOLD_DAYS
    away_for = datetime.now(timezone.utc) - seen
    return away_for >= timedelta(days=threshold_days)


def _gather_recent_activity(user: dict, workspace: str, since: datetime) -> list[str]:
    """Sharing-aware summary lines of what changed since `since`, across the
    v1 module set. Each block goes through the same access-checked function
    the real page/endpoint uses — see module docstring."""
    lines: list[str] = []
    since_iso = since.isoformat()
    user_name = user["name"]
    role = user.get("feature_role", "member")
    is_admin = user.get("role") == "admin"

    from services import task_service

    tasks = task_service.list_tasks(user_name, workspace)
    completed = [t for t in tasks if (t.get("completed_at") or "") >= since_iso]
    created = [t for t in tasks if (t.get("created_at") or "") >= since_iso]
    if completed:
        lines.append(
            f"Completed {len(completed)} task(s): " + ", ".join(t["title"] for t in completed[:10])
        )
    if created:
        lines.append(
            f"Added {len(created)} new task(s): " + ", ".join(t["title"] for t in created[:10])
        )

    from module_packages.journal.backend import service as journal_service

    # Own journal only — journal is never shareable anywhere in this app.
    entries = journal_service.list_entries(user_name, workspace)
    recent_entries = [e for e in entries if e.get("date", "") >= since.date().isoformat()]
    if recent_entries:
        lines.append(
            f"Wrote {len(recent_entries)} journal entr{'y' if len(recent_entries) == 1 else 'ies'}"
        )

    from services import notes_service

    notes = notes_service.list_visible_notes(user_name, role, is_admin, workspace)
    recent_notes = [
        n for n in notes if (n.get("updated_at") or n.get("created_at") or "") >= since_iso
    ]
    if recent_notes:
        lines.append(
            f"{len(recent_notes)} note(s) changed: "
            + ", ".join(n.get("name", "untitled") for n in recent_notes[:10])
        )

    from services import events_service

    events = events_service.list_events(user_name, workspace)
    upcoming = [
        e
        for e in events
        if (e.get("start_date") or "") >= datetime.now(timezone.utc).date().isoformat()
    ]
    if upcoming:
        lines.append(f"{len(upcoming)} upcoming event(s) on the calendar")

    return lines


async def generate_summary(user: dict, workspace: str = "personal") -> str | None:
    """AI-generated natural-language summary of what changed while the user
    was away, or None if the AI isn't configured, the setting is off, or
    there's nothing worth summarizing. Caller (the router) is responsible for
    checking `should_show()` and the user's own
    welcome_back_ai_summary_enabled setting before calling this."""
    from services.ai_provider import chat_completion, is_ai_configured

    if not is_ai_configured():
        return None

    seen_at = presence_service.last_seen_iso(user["name"])
    if not seen_at:
        return None
    try:
        since = datetime.fromisoformat(seen_at)
    except ValueError:
        return None

    lines = _gather_recent_activity(user, workspace, since)
    if not lines:
        return None

    system = (
        "You are the AI layer of LogCore Brain, a personal life operating system. "
        "The user is returning after being away. Write a short (2-4 sentence), warm, "
        "specific welcome-back summary of what changed while they were gone, based only "
        "on the activity data given. Do not invent details not present in the data."
    )
    messages = [
        {
            "role": "user",
            "content": "Recent activity while away:\n" + "\n".join(f"- {l}" for l in lines),
        }
    ]
    try:
        return await chat_completion(
            system, messages, max_tokens=300, user_name=user["name"], workspace=workspace
        )
    except Exception:
        return None  # AI summary is a nicety — never block the popup itself on a provider error
