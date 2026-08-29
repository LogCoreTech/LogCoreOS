"""Module registry — discovers module_packages/<id>/ manifests and wires active
ones into the running app. This is the mechanism every future module install/
uninstall/conversion rides on; see docs/MEMORY.md for the design rationale.

SECURITY: discover_manifests() imports arbitrary Python via importlib — this is
safe ONLY because module_packages/ is first-party, reviewed code shipped with
core releases (never a community-submission surface). If that trust model ever
changes, this whole mechanism needs a different design (sandboxing, static
analysis, a signing/review gate) — not just an added checkbox.
"""

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

logger = logging.getLogger("logcore.module_registry")

MigrationFn = Callable[[Path], None]

_PACKAGES_DIR = Path(__file__).parent / "module_packages"


@dataclass
class MetricProviderSpec:
    """A source of live "current value vs. target -> percent" data another
    module can register for Goals' metric picker, WITHOUT Goals containing
    any module-specific logic of its own — the same generic-registry shape
    as owned_agent_tools/owned_block_types, applied to metrics. Declared on
    the OWNING module's own manifest (e.g. Finance declares its own budget
    provider), never on Goals'.

    `key` only needs to be unique within the owning module — Goals'
    metric_providers() below namespaces it as f"{module_id}:{key}" the same
    way migration names are namespaced, so two modules can each have their
    own "manual"-ish key without colliding.

    `config_schema` is a list of {key, label, kind, ...} field descriptors —
    the same shape blockRegistry.js's CONFIG_FIELD_SCHEMAS already uses on
    the frontend, so the existing kind-based picker dispatch
    (BlockPicker.jsx's renderField) can render this provider's config form
    with zero new frontend picker-dispatch mechanism, only new `kind`
    entries where a genuinely new picker is needed (e.g. a number-type
    field picker).

    `resolve(config, user, workspace)` returns {"current": float,
    "target": float | None, "pct": int} — computed live on every call, same
    as finance_planning_service.budget_status()'s own "no persisted
    percent" precedent. Must never raise for ordinary "no data yet" cases
    (return current=0/target=None/pct=0 instead) — a broken provider should
    degrade one goal's display, never crash Goals' own list/get endpoints."""

    key: str
    label: str
    config_schema: list[dict]
    resolve: Callable[[dict, dict, str], dict]


@dataclass
class ModuleManifest:
    id: str
    display_name: str
    description: str
    icon: str
    version: str
    router_prefix: str
    router_tags: list[str]
    get_router: Callable[[], "APIRouter"]
    owned_brain_paths: list[str] = field(default_factory=list)
    owned_agent_tools: list[str] = field(default_factory=list)
    read_only_agent_tools: list[str] = field(default_factory=list)
    admin_agent_tools: list[str] = field(default_factory=list)
    owned_block_types: list[str] = field(default_factory=list)
    owned_metric_providers: list[MetricProviderSpec] = field(default_factory=list)
    migrations: list[tuple[str, MigrationFn]] = field(default_factory=list)
    uninstallable: bool = False
    on_install: Callable[[Path], None] | None = None
    on_new_user: Callable[[Path, str], None] | None = None
    help_section: dict | None = None


class LockedModuleRegistrationError(RuntimeError):
    """A locked (uninstallable) module failed to register — boot-critical."""


def discover_manifests() -> tuple[dict[str, ModuleManifest], dict[str, str]]:
    """Scan module_packages/*/manifest.py and import each via importlib.

    Returns (manifests, errors) — a module whose manifest fails to import or
    collides on a migration name is recorded in `errors`, never raised, never
    crashes discovery. Discovery order (and therefore error precedence) is
    alphabetical by directory name for determinism.
    """
    manifests: dict[str, ModuleManifest] = {}
    errors: dict[str, str] = {}

    if not _PACKAGES_DIR.exists():
        return manifests, errors

    candidates = sorted(
        p.name
        for p in _PACKAGES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("_") and (p / "manifest.py").is_file()
    )
    for entry in candidates:
        try:
            mod = importlib.import_module(f"module_packages.{entry}.manifest")
            manifest = mod.MODULE
            if manifest.id != entry:
                raise ValueError(
                    f"manifest.id {manifest.id!r} does not match directory name {entry!r}"
                )
            manifests[entry] = manifest
        except Exception as exc:
            logger.exception("module_packages/%s: manifest failed to import", entry)
            errors[entry] = str(exc)

    _check_migration_collisions(manifests, errors)
    return manifests, errors


def _check_migration_collisions(
    manifests: dict[str, ModuleManifest], errors: dict[str, str]
) -> None:
    """Exclude (from `manifests`, into `errors`) any module whose migration
    name collides with core's or another module's. Low real risk given
    first-party-only authorship, but cheap insurance now that this system
    anticipates many modules eventually sharing one migration namespace."""
    from migrations.runner import MIGRATIONS as CORE_MIGRATIONS

    seen: dict[str, str] = {name: "core" for name, _ in CORE_MIGRATIONS}
    for module_id in list(manifests.keys()):
        manifest = manifests[module_id]
        for name, _fn in manifest.migrations:
            owner = seen.get(name)
            if owner is not None:
                logger.error(
                    "module_packages/%s: migration name %r collides with %s — module excluded",
                    module_id,
                    name,
                    owner,
                )
                errors[module_id] = f"migration name collision: {name!r} (already used by {owner})"
                del manifests[module_id]
                break
            seen[name] = module_id


def read_only_agent_tool_names() -> set[str]:
    """Union of read_only_agent_tools across every ACTIVE module — feeds
    agent_service.py's _RESEARCH_TOOLS/_READ_TOOLS sets so a module's
    genuinely read-only tools (e.g. read_journal_entry) work in research
    mode and run without approval in approve mode, same as any core
    read-only tool. A tool NOT listed here defaults to write-gated even if
    it's in owned_agent_tools — matches this codebase's existing
    "new tools are write-gated by default" rule, just extended to modules."""
    names: set[str] = set()
    for manifest in active_manifests().values():
        names.update(manifest.read_only_agent_tools)
    return names


def admin_agent_tool_names() -> set[str]:
    """Union of admin_agent_tools across every ACTIVE module — feeds
    agent_service.py's _get_tools() so a module's admin-only tools (e.g.
    household's shared-task management tools) are only OFFERED to admin
    callers, mirroring how core's own _ADMIN_TOOLS list is only added for
    an admin caller. A tool NOT listed here is offered to every
    module-enabled user regardless of role — the executor itself may still
    enforce a finer-grained check on top (e.g. complete_shared_task's
    admin-or-assignee check), this field only controls whether the tool's
    SCHEMA is even offered to the model in the first place. First needed by
    household's 2026-08-25 conversion — no prior converted module owned an
    admin-only tool, so offering every owned_agent_tools schema to every
    module-enabled user (regardless of role) was correct until now."""
    names: set[str] = set()
    for manifest in active_manifests().values():
        names.update(manifest.admin_agent_tools)
    return names


def directional_pct(
    current: float, target: float | None, direction: str = "increase", start_value: float | None = None
) -> int:
    """0-100 progress toward `target`, aware of which way progress moves —
    shared by every MetricProviderSpec.resolve() that needs it (Goals' own
    "manual" provider, Contacts' "weight" provider) rather than defined
    per-module, since it's pure math with no module-specific logic at all.
    Lives here (not inside module_packages/goals/) so a module registering
    its OWN metric provider (e.g. Contacts) doesn't have to import from a
    sibling module's package just for this formula.

    "increase" (default, e.g. pages read, savings): progress = how far
    `current` has moved UP from `start_value` (default 0) toward `target`.
    "decrease" (e.g. weight loss, debt payoff, screen time reduction):
    progress = how far `current` has moved DOWN from `start_value` toward
    `target` — get this backwards (plain current/target) and a weight-loss
    goal shows WORSE as you actually lose weight, which is why this exists
    as its own shared helper rather than being inlined per-provider.

    `start_value` unset defaults to 0 for "increase" (matches the original,
    pre-direction behavior) and to `current` for "decrease" (a goal just
    configured with no explicit starting point reads as 0% until the value
    actually moves, rather than crashing or guessing)."""
    if target is None:
        return 0
    if direction == "decrease":
        start = start_value if start_value is not None else current
        denom = start - target
        pct = (start - current) * 100 / denom if denom else 0
    else:
        start = start_value if start_value is not None else 0
        denom = target - start
        pct = (current - start) * 100 / denom if denom else 0
    return max(0, min(100, round(pct)))


def metric_providers() -> dict[str, MetricProviderSpec]:
    """Every metric provider registered by an ACTIVE module, keyed by
    f"{module_id}:{provider.key}" — the mechanism Goals' own metric picker
    discovers providers through. Goals has zero module-specific code here;
    it just calls this and lists whatever comes back, the same discovery
    shape as read_only_agent_tool_names()/admin_agent_tool_names() above.
    A provider whose owning module gets disabled/uninstalled simply stops
    appearing — any goal still configured to use it keeps its stored
    config, but resolve() is never called for a provider that isn't
    currently active (the caller is expected to treat a missing key the
    same as "no data available" rather than erroring)."""
    providers: dict[str, MetricProviderSpec] = {}
    for module_id, manifest in active_manifests().items():
        for spec in manifest.owned_metric_providers:
            providers[f"{module_id}:{spec.key}"] = spec
    return providers


def brain_paths_for_disabled(disabled_modules: set[str]) -> set[str]:
    """Union of owned_brain_paths for every DISCOVERED module whose id is in
    `disabled_modules` — the shared piece of "which Brain folders should be
    hidden from generic access for THIS user" logic, used by both
    routers/brain.py's file browser skip-list and agent_service.py's AI tool
    scoping. Lives here rather than in either of those (services never
    import from routers, and this needs to be callable from both).

    Deliberately per-user, not instance-wide: `disabled_modules` should be
    the caller's already-resolved get_effective_disabled() result, which
    already unions role-disabled + per-user-override + not-installed-at-all
    — a module can be installed instance-wide and still disabled for one
    particular role/user, and that case must hide its folder here too, the
    same as the not-installed case.
    """
    manifests, _errors = discover_manifests()
    paths: set[str] = set()
    for module_id, manifest in manifests.items():
        if module_id in disabled_modules:
            paths.update(manifest.owned_brain_paths)
    return paths


def active_manifests() -> dict[str, ModuleManifest]:
    """Discovered manifests filtered to what's actually installed. A locked
    (uninstallable=True) module is always installed by construction — its own
    upgrade migration seeds installed_modules.json unconditionally."""
    from services import mod_store_service

    manifests, _errors = discover_manifests()
    installed = mod_store_service.get_installed_ids()
    return {mid: m for mid, m in manifests.items() if mid in installed}


def register_routers(app: "FastAPI") -> set[str]:
    """Register every active module's router. Called after all core routers,
    before the SPA catch-all. Returns the set of module ids actually
    registered this boot — the caller (main.py) caches this on app.state so
    GET /mod-store/active can report what's REALLY live in the running
    process, distinct from GET /mod-store/installed (the marker file, which
    can say "installed" before the next restart has picked it up).

    Failure handling is asymmetric by design: an optional module's
    registration failure is logged and skipped (one broken optional module
    never takes down the app, mirroring main.py's _warm_share_index()
    pattern). A LOCKED module's failure is boot-critical — it crashes startup
    loudly, matching today's behavior where a broken hardcoded import already
    crashes the app. Leaving a deeply load-bearing module (Tasks, Chat,
    Dashboards) silently unregistered would make the app LOOK healthy while a
    core feature is actually missing — worse than a crash, not better.
    """
    registered: set[str] = set()
    for module_id, manifest in active_manifests().items():
        try:
            router = manifest.get_router()
            app.include_router(router, prefix=manifest.router_prefix, tags=manifest.router_tags)
            registered.add(module_id)
            logger.info(
                "module_packages/%s: router registered at %s", module_id, manifest.router_prefix
            )
        except Exception as exc:
            if manifest.uninstallable:
                raise LockedModuleRegistrationError(
                    f"Locked module {module_id!r} failed to register its router — "
                    "refusing to start, since this app cannot function correctly "
                    "without it."
                ) from exc
            logger.exception(
                "module_packages/%s: router registration failed — module unavailable this boot",
                module_id,
            )
    return registered
