"""App-wide search fan-out — services/search_service.py stays core using the
same test tags_service.py already passes: zero owning module by
construction, consumed only by the thin HTTP layer (routers/search.py).

Live fan-out, no persisted index — matches the RAG project's own locked
design rule (a derived index must be a disposable cache, never source of
truth) applied one level earlier: this is the plain-substring, always-fresh
precursor to that eventual semantic layer, the same relationship
agent_service.py's own search_brain already has to Brain markdown
specifically, just generalized across every module's own JSON/markdown data
instead of only markdown.

Each module owns its own SearchProviderSpec.resolve() (declared on that
module's own manifest.py) — this file contains zero module-specific
logic, only discovery + generic fan-out + disabled-module filtering.

2026-09-04 UX Polish Batch item #10 (fast-follow): cross-workspace search
and per-provider "show more" pagination, added via new keyword-only params
that all default to the pre-existing behavior — `search()` still returns a
plain `list[dict]` unless `with_totals=True` is passed, so every existing
caller/test is unaffected. Real relevance ranking across providers is
explicitly NOT part of this item — that's the roadmapped RAG project's own
job."""

import logging

import module_registry

logger = logging.getLogger("logcore.search_service")

_PER_PROVIDER_CAP = 20
_TOTAL_CAP = 60
_SHOW_MORE_CAP = 100  # single-provider "show more" fetch, uncapped by _TOTAL_CAP


def search(
    query: str,
    tags: list[str],
    user: dict,
    workspace: str,
    *,
    cross_workspace: bool = False,
    provider: str | None = None,
    with_totals: bool = False,
) -> list[dict] | dict:
    """Fan out to every active module's own search provider, skipping any
    module currently disabled for this user. `user["disabled_modules"]` is
    already the fully-resolved effective set by the time a request reaches
    here (routers/auth.py's get_current_user() computes it via
    get_effective_disabled() before returning the user dict), so no second
    resolution is needed — same convention agent_service.py's _brain_skip()
    already relies on.

    Returns a plain `list[dict]` by default (unchanged pre-existing
    contract). Pass `with_totals=True` to instead get
    `{"results": [...], "provider_totals": {namespaced_key: total}}` — the
    "show more" affordance needs to know each provider's real total, not
    just the capped count returned.

    Every result carries its own `_workspace` — always the single searched
    `workspace` unless `cross_workspace=True`, in which case every
    workspace the user has access to (`user["workspaces"]`) is searched and
    tagged with which one it came from, each provider run once per
    workspace (a provider's own resolve() already scopes its data reads by
    the workspace string passed to it, so this can't double-count within
    one workspace).

    `provider` (a namespaced key like "tasks:tasks") narrows to just that
    one provider at a higher cap (`_SHOW_MORE_CAP`, not `_TOTAL_CAP`) — the
    "show more" fetch for a single provider's own truncated result set, not
    a second global search.

    Returns no results immediately for an empty query AND empty tags —
    there's no "browse everything" mode here, only "search for X" and/or
    "filter by tag Y". A provider that raises degrades to zero results from
    that module only; it never takes down the rest of the response."""
    empty: list[dict] | dict = {"results": [], "provider_totals": {}} if with_totals else []
    if not query.strip() and not tags:
        return empty

    disabled = set(user.get("disabled_modules") or [])
    workspaces = user.get("workspaces", ["personal"]) if cross_workspace else [workspace]

    results: list[dict] = []
    provider_totals: dict[str, int] = {}
    for ws in workspaces:
        for namespaced_key, spec in module_registry.search_providers().items():
            if provider and namespaced_key != provider:
                continue
            owning_module = namespaced_key.split(":", 1)[0]
            if owning_module in disabled:
                continue
            try:
                provider_results = spec.resolve(query, tags, user, ws)
            except Exception:
                logger.exception("search provider %s failed", namespaced_key)
                continue
            cap = _SHOW_MORE_CAP if provider else _PER_PROVIDER_CAP
            provider_totals[namespaced_key] = provider_totals.get(namespaced_key, 0) + len(
                provider_results
            )
            for r in provider_results[:cap]:
                results.append(
                    {**r, "_module": owning_module, "_workspace": ws, "_provider": namespaced_key}
                )

    capped = results if provider else results[:_TOTAL_CAP]
    if with_totals:
        return {"results": capped, "provider_totals": provider_totals}
    return capped
