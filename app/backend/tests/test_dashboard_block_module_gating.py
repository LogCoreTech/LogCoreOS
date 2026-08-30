"""Enforcement-gap tests for dashboard blocks: a block type owned by a
disabled module must be excluded from the catalog (block picker) and must
fail to render (locked_reason="module_disabled") — even though the
underlying data still exists — with the gate applied to whichever identity
render_block() is actually resolving as at that pass (viewer at pass 1,
owner at pass 2's share_underlying_data exception)."""

from services import auth_service, mod_store_service
from services.dashboard_blocks import registry
from services.dashboard_blocks.render import render_block

_DASHBOARD_BLOCK_SRC = """
from services.dashboard_blocks.registry import BlockSpec, BlockRenderResult, register

def _resolve(ctx):
    return BlockRenderResult(ok=True, data={"resolved_as": ctx.viewer})

register(BlockSpec(
    type="t_gate_block",
    label="Test Gate Block",
    category="freeform",
    resolver=_resolve,
    module="t_dash_gate",
))
"""

_MANIFEST_SRC = """
from module_registry import ModuleManifest

def _get_router():
    from module_packages.t_dash_gate.backend.router import router
    return router

MODULE = ModuleManifest(
    id="t_dash_gate",
    display_name="Test",
    description="Test",
    icon="x",
    version="0.0.1",
    router_prefix="/api/v1/t_dash_gate",
    router_tags=["t_dash_gate"],
    get_router=_get_router,
)
"""


def test_catalog_excludes_block_owned_by_disabled_module(fake_module):
    fake_module("t_dash_gate", _MANIFEST_SRC, dashboard_block_src=_DASHBOARD_BLOCK_SRC)
    registry._load_all_resolvers()
    try:
        cat_disabled = registry.catalog(is_admin=False, disabled_modules={"t_dash_gate"})
        assert "t_gate_block" not in {c["type"] for c in cat_disabled}

        cat_enabled = registry.catalog(is_admin=False, disabled_modules=set())
        assert "t_gate_block" in {c["type"] for c in cat_enabled}
    finally:
        registry.REGISTRY.pop("t_gate_block", None)


def test_render_block_locks_when_viewer_owns_and_module_disabled(fake_module):
    fake_module("t_dash_gate", _MANIFEST_SRC, dashboard_block_src=_DASHBOARD_BLOCK_SRC)
    registry._load_all_resolvers()
    try:
        dashboard = {"owner": "alice", "share_underlying_data": False}
        block = {"id": "b1", "type": "t_gate_block", "config": {}}

        result = render_block(
            dashboard,
            block,
            "alice",
            "member",
            False,
            "personal",
            "edit",
            viewer_disabled_modules={"t_dash_gate"},
        )
        assert result.ok is False
        assert result.locked_reason == "module_disabled"
    finally:
        registry.REGISTRY.pop("t_gate_block", None)


def test_render_block_resolves_when_viewer_owns_and_module_enabled(fake_module):
    fake_module("t_dash_gate", _MANIFEST_SRC, dashboard_block_src=_DASHBOARD_BLOCK_SRC)
    registry._load_all_resolvers()
    try:
        dashboard = {"owner": "alice", "share_underlying_data": False}
        block = {"id": "b1", "type": "t_gate_block", "config": {}}

        result = render_block(
            dashboard,
            block,
            "alice",
            "member",
            False,
            "personal",
            "edit",
            viewer_disabled_modules=set(),
        )
        assert result.ok is True
        assert result.data == {"resolved_as": "alice"}
    finally:
        registry.REGISTRY.pop("t_gate_block", None)


def test_render_block_falls_back_to_owner_when_viewer_disabled_but_owner_enabled(
    fake_module, brain
):
    """share_underlying_data on, viewer's own copy of the module is off, but
    the OWNER's is on (module installed instance-wide, owner has no personal
    override) — pass 2 should resolve as the owner, per the existing
    share_underlying_data exception mechanism."""
    fake_module("t_dash_gate", _MANIFEST_SRC, dashboard_block_src=_DASHBOARD_BLOCK_SRC)
    registry._load_all_resolvers()
    mod_store_service.mark_installed("t_dash_gate", by="tester")  # installed instance-wide

    owner = auth_service.create_user("owner@example.com", "password123", "Owner")
    try:
        dashboard = {"owner": "Owner", "share_underlying_data": True}
        block = {"id": "b1", "type": "t_gate_block", "config": {}}

        result = render_block(
            dashboard,
            block,
            "viewer_name",
            "member",
            False,
            "personal",
            "read",
            viewer_disabled_modules={"t_dash_gate"},
        )
        assert result.ok is True
        assert result.data == {"resolved_as": "Owner"}
    finally:
        registry.REGISTRY.pop("t_gate_block", None)


def test_render_block_locks_when_both_viewer_and_owner_have_it_disabled(fake_module, brain):
    """share_underlying_data on, but the module isn't installed instance-wide
    at all — both viewer and owner are disabled (not_installed applies to
    everyone), so pass 2 must also stay locked, not silently succeed."""
    fake_module("t_dash_gate", _MANIFEST_SRC, dashboard_block_src=_DASHBOARD_BLOCK_SRC)
    registry._load_all_resolvers()
    # deliberately never marked installed

    owner = auth_service.create_user("owner2@example.com", "password123", "Owner2")
    try:
        dashboard = {"owner": "Owner2", "share_underlying_data": True}
        block = {"id": "b1", "type": "t_gate_block", "config": {}}

        result = render_block(
            dashboard,
            block,
            "viewer_name",
            "member",
            False,
            "personal",
            "read",
            viewer_disabled_modules={"t_dash_gate"},
        )
        assert result.ok is False
        assert result.locked_reason == "module_disabled"
    finally:
        registry.REGISTRY.pop("t_gate_block", None)
