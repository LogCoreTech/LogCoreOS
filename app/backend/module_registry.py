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
    owned_block_types: list[str] = field(default_factory=list)
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
