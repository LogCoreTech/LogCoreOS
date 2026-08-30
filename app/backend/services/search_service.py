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
logic, only discovery + generic fan-out + disabled-module filtering."""

import logging

import module_registry

logger = logging.getLogger("logcore.search_service")

_PER_PROVIDER_CAP = 20
_TOTAL_CAP = 60


def search(query: str, tags: list[str], user: dict, workspace: str) -> list[dict]:
    """Fan out to every active module's own search provider, skipping any
    module currently disabled for this user. `user["disabled_modules"]` is
    already the fully-resolved effective set by the time a request reaches
    here (routers/auth.py's get_current_user() computes it via
    get_effective_disabled() before returning the user dict), so no second
    resolution is needed — same convention agent_service.py's _brain_skip()
    already relies on.

    Returns [] immediately for an empty query AND empty tags — there's no
    "browse everything" mode here, only "search for X" and/or "filter by
    tag Y". A provider that raises degrades to zero results from that
    module only; it never takes down the rest of the response."""
    if not query.strip() and not tags:
        return []

    disabled = set(user.get("disabled_modules") or [])
    results: list[dict] = []
    for namespaced_key, spec in module_registry.search_providers().items():
        owning_module = namespaced_key.split(":", 1)[0]
        if owning_module in disabled:
            continue
        try:
            provider_results = spec.resolve(query, tags, user, workspace)
        except Exception:
            logger.exception("search provider %s failed", namespaced_key)
            continue
        for r in provider_results[:_PER_PROVIDER_CAP]:
            results.append({**r, "_module": owning_module})

    return results[:_TOTAL_CAP]
