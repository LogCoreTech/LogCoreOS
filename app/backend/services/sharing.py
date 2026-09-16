"""Shared helper for the accept/decline share-response pattern used by
Assets, Finance, Contacts, Notes, and Dashboard(-Templates) sharing.

This deliberately does NOT unify every service's sharing model into one
generic resolver — Finance's book+account 2-level nesting, Notes' sidecar
+ancestor-walk, Contacts' self_of/created_by escape hatches, Assets' pool
named_only manager-downgrade, and incompatible per-service `caps` schemas
are too structurally different to share cleanly (see docs/MEMORY.md's
2026-09-07 audit for the full reasoning). Each service still owns its own
storage shape and its own target-expansion function (group/role/user name
resolution differs per service).

What IS shared, and was found MISSING from Assets' and Dashboard Templates'
own respond-to-share logic (a real, live-PoC-confirmed privilege-escalation
bug, fixed 2026-09-08): the one check that an accept/decline actually
targets the responding viewer before that entry's `accepted` list is
touched at all. Without it, ANY recipient of ANY share notification on a
node gets silently added to `accepted[]` on EVERY request-based entry on
that same node — including ones granting a completely different person a
higher access level. Finance's/Contacts'/Notes' own `respond_share()`
functions already had this check; this file is that same, already-correct
logic, extracted so Assets and Dashboard Templates can use it instead of
each carrying their own unchecked copy.
"""

from __future__ import annotations

from typing import Callable


def entry_targets_viewer(
    entry: dict, viewer: str, resolve_target_users: Callable[[str], list[str]]
) -> bool:
    """True if `entry`'s own `target` (a user name, a group like 'team'/
    'household', or a role) actually expands to include `viewer`.
    `resolve_target_users` is the calling service's own target-expansion
    function — a `ValueError` from an unresolvable/stale target is treated
    as "doesn't target anyone," matching every existing correct caller's
    own error handling (rather than letting a stale/malformed target
    accidentally match everyone)."""
    try:
        return viewer in resolve_target_users(entry.get("target", ""))
    except ValueError:
        return False


def apply_share_response(
    entries: list[dict],
    viewer: str,
    accept: bool,
    resolve_target_users: Callable[[str], list[str]],
) -> tuple[list[dict], bool]:
    """Apply an accept/decline to a list of share entries. Accept adds
    `viewer` to a targeting entry's `accepted[]`; decline removes them,
    dropping the entry entirely if it named `viewer` directly (a per-user
    share — the owner shouldn't keep listing someone who left). An entry
    with no `accepted` key at all (no handshake ever started on it) is left
    untouched. **Only entries whose `target` actually resolves to `viewer`
    are ever touched** — this is the fix: every entry used to be eligible
    just by having an `accepted` key, regardless of who it actually named.

    Returns `(new_entries, changed)`, mirroring Finance's/Contacts'/Notes'
    own already-correct `respond_share()` shape exactly."""
    kept: list[dict] = []
    changed = False
    for entry in entries:
        if "accepted" not in entry:
            kept.append(entry)
            continue
        if not entry_targets_viewer(entry, viewer, resolve_target_users):
            kept.append(entry)
            continue
        if not accept and entry.get("target") == viewer:
            changed = True  # per-user share declined/left → drop the entry entirely
            continue
        accepted = entry["accepted"]
        if accept and viewer not in accepted:
            accepted.append(viewer)
            changed = True
        elif not accept and viewer in accepted:
            accepted.remove(viewer)
            changed = True
        kept.append(entry)
    return kept, changed
