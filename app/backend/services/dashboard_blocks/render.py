"""The security-critical core: renders every block on a dashboard through the
registry, enforcing the read-through-never-a-bypass rule and its one deliberate
exception (share_underlying_data). See docs/MEMORY.md for the full design
rationale once this ships — this is the single highest-consequence code path
in the whole Dashboards feature; a bug here can leak real data, not just show
a UI glitch.
"""

from services import auth_service
from services.dashboard_blocks.registry import REGISTRY, BlockRenderCtx, BlockRenderResult, _load_all_resolvers

_load_all_resolvers()


def render_block(
    dashboard: dict,
    block: dict,
    viewer: str,
    viewer_role: str,
    is_admin: bool,
    workspace: str,
    dash_access: str | None,
) -> BlockRenderResult:
    spec = REGISTRY.get(block.get("type"))
    if spec is None:
        return BlockRenderResult(ok=False, locked_reason="not_found")

    owner = dashboard.get("owner", "")
    share_on = bool(dashboard.get("share_underlying_data"))
    can_exception = share_on and viewer != owner and dash_access in ("read", "contribute", "edit")

    if spec.admin_only and not is_admin and not can_exception:
        return BlockRenderResult(ok=False, locked_reason="admin_only")

    # Pass 1 — always resolve as the viewer's own identity first. This is the
    # ONLY path exercised when share_underlying_data is off, and it never
    # special-cases block type: every resolver independently re-checks access
    # via that module's own gate.
    ctx = BlockRenderCtx(
        viewer=viewer,
        viewer_role=viewer_role,
        is_admin=is_admin,
        workspace=workspace,
        config=block.get("config") or {},
        dashboard_owner=owner,
    )
    try:
        result = spec.resolver(ctx)
    except Exception:
        return BlockRenderResult(ok=False, locked_reason="not_found")

    if result.ok or not can_exception:
        return result

    # Pass 2 — the ONE exception. Re-run the SAME resolver as the owner's
    # identity. Structural guarantee, not a per-block-type rule: the viewer can
    # never see more than the owner independently can — if the owner's own
    # access has since been revoked, owner_result.ok is False and the block
    # stays locked for every shared viewer too, automatically.
    owner_user = auth_service.get_user_by_name(owner)
    if owner_user is None:
        return result  # fail closed — owner account gone
    owner_ctx = BlockRenderCtx(
        viewer=owner,
        viewer_role=owner_user.get("feature_role", "member"),
        is_admin=owner_user.get("role") == "admin",
        workspace=workspace,
        config=block.get("config") or {},
        dashboard_owner=owner,
    )
    try:
        owner_result = spec.resolver(owner_ctx)
    except Exception:
        return BlockRenderResult(ok=False, locked_reason="not_found")
    if not owner_result.ok and not owner_result.locked_reason:
        owner_result.locked_reason = "owner_lost_access"
    return owner_result


def render_dashboard(
    dashboard: dict, viewer: str, viewer_role: str, is_admin: bool, workspace: str, dash_access: str | None
) -> list[dict]:
    """Resolves dash_access is passed in ONCE by the caller (routers/dashboards.py
    already called find_dashboard) — never re-resolved per block."""
    out = []
    for block in dashboard.get("blocks") or []:
        result = render_block(dashboard, block, viewer, viewer_role, is_admin, workspace, dash_access)
        out.append(
            {
                "id": block["id"],
                "type": block["type"],
                "config": block.get("config") or {},
                "layout": block.get("layout") or {},
                "ok": result.ok,
                "data": result.data,
                "locked_reason": result.locked_reason,
            }
        )
    return out
