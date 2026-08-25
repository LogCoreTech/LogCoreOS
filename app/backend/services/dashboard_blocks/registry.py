"""Block-type registry — the single source of truth for what block types exist,
what they render, whether they're admin-only, and which config keys point at
which module's records (used by dashboard_index.py to build reverse lookups
without any per-block-type hardcoding there).
"""

from dataclasses import dataclass, field
from typing import Callable, Literal


@dataclass
class BlockRenderCtx:
    viewer: str
    viewer_role: str
    is_admin: bool
    workspace: str
    config: dict
    dashboard_owner: str


@dataclass
class BlockRenderResult:
    ok: bool
    data: dict | None = None
    locked_reason: str | None = (
        None  # "no_access" | "admin_only" | "not_found" | "owner_lost_access" | "module_disabled"
    )


@dataclass
class BlockSpec:
    type: str
    label: str
    category: Literal["live_aggregate", "record_linked", "freeform"]
    resolver: Callable[[BlockRenderCtx], BlockRenderResult]
    admin_only: bool = False
    workspace: str | None = None  # None = both
    scope_configurable: bool = False
    record_ref_fields: dict[str, str] = field(default_factory=dict)  # {"asset_id": "assets"}
    module: str | None = None  # owning module_packages/ id, if any — feeds module-disabled gating


REGISTRY: dict[str, BlockSpec] = {}


def register(spec: BlockSpec) -> None:
    REGISTRY[spec.type] = spec


def catalog(is_admin: bool, disabled_modules: set[str] | None = None) -> list[dict]:
    """Metadata for the frontend block picker — admin-only types are simply
    omitted for a non-admin caller (defense in depth on top of the render-time
    gate in render.py). A block type owned by a disabled/uninstalled module is
    omitted the same way."""
    disabled = disabled_modules or set()
    out = []
    for spec in REGISTRY.values():
        if spec.admin_only and not is_admin:
            continue
        if spec.module and spec.module in disabled:
            continue
        out.append(
            {
                "type": spec.type,
                "label": spec.label,
                "category": spec.category,
                "admin_only": spec.admin_only,
                "workspace": spec.workspace,
                "scope_configurable": spec.scope_configurable,
            }
        )
    return out


def _load_all_resolvers() -> None:
    """Import every resolver module once so their register() calls run —
    core resolvers first, then each discovered module_packages/ module's own
    dashboard_block.py (if it has one), same try/except-per-module isolation
    register_routers() uses so one broken module never blocks the rest."""
    import logging

    from services.dashboard_blocks import (  # noqa: F401
        _actions,
        _ai_usage,
        _assets,
        _automations,
        _calendar,
        _collections,
        _contacts,
        _finance,
        _freeform,
        _notes,
        _pool,
        _tasks,
    )

    logger = logging.getLogger("logcore.dashboard_blocks")
    from module_registry import discover_manifests

    manifests, _errors = discover_manifests()
    for module_id in manifests:
        try:
            import importlib

            importlib.import_module(f"module_packages.{module_id}.backend.dashboard_block")
        except ModuleNotFoundError:
            pass  # this module has no dashboard blocks — fine
        except Exception:
            logger.exception(
                "module_packages/%s: dashboard_block failed to import — its block "
                "type(s) unavailable this boot",
                module_id,
            )
