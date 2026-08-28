"""AI agent tools owned by the dashboard module — TOOL_SCHEMAS is folded into
_get_tools()'s returned list (filtered by disabled_modules first, then
list_dashboards/get_dashboard/list_dashboard_templates/
get_dashboard_block_catalog additionally feed research_tools/_READ_TOOLS via
the manifest's read_only_agent_tools), and execute() is what agent_service.py's
tool executor falls back to for any name its own core match/case doesn't
handle. Returning None means "not one of mine" so the dispatcher can try the
next module.

All 10 tools were already workspace-aware inline (the pre-conversion case
branches all threaded `workspace` through dashboards_service calls) — the
generic dispatch signature was already widened for this during notes/'s own
conversion the day before, so no further mechanism change was needed here,
just the move."""

import uuid

TOOL_SCHEMAS = [
    {
        "name": "list_dashboards",
        "description": "List dashboards visible to the user (own + workspace pool + shared-to-them), each annotated with access level and, if applicable, its template.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_dashboard",
        "description": "Get one dashboard's blocks, including each one's current position and size on the desktop grid (36 columns wide, 24px rows) — call this before update_dashboard_block if you're moving or resizing an existing block, so you can see what's already occupied and pick a spot that doesn't overlap another block.",
        "input_schema": {
            "type": "object",
            "properties": {"dashboard_id": {"type": "string"}},
            "required": ["dashboard_id"],
        },
    },
    {
        "name": "list_dashboard_templates",
        "description": "List dashboard templates the user can build a new dashboard from (role-permitted global + their own personal + shared-and-accepted).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_dashboard_block_catalog",
        "description": "List every dashboard block type (label, category, admin_only) together with its config_fields — the exact keys/kinds needed to configure it for add_dashboard_block/update_dashboard_block. Call this before adding or editing a block if you don't already know its config shape.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "create_dashboard",
        "description": "Create a new dashboard, blank or from a template. pool=true creates a shared household/team dashboard (admin only) instead of a personal one.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "icon": {"type": "string", "description": "Optional emoji"},
                "template_id": {
                    "type": "string",
                    "description": "Optional — build from this template's block set",
                },
                "subject_id": {
                    "type": "string",
                    "description": "Required if the template has a subject_type — the contact or asset id this dashboard is about",
                },
                "pool": {
                    "type": "boolean",
                    "description": "true = shared household/team dashboard (admin only)",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "add_dashboard_block",
        "description": "Add a block to a dashboard. Requires contribute or edit access. Fails if the dashboard uses a template — its block set is template-controlled (edit the template instead, or use update_dashboard_template). Call get_dashboard_block_catalog first if you don't already know the block type's config shape. The new block is stacked at the bottom automatically — position (x/y) is never set here, only size is optionally controllable via `layout`.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "string"},
                "type": {
                    "type": "string",
                    "description": "A block type from get_dashboard_block_catalog",
                },
                "config": {
                    "type": "object",
                    "description": "Config keys per get_dashboard_block_catalog's config_fields for this type",
                },
                "layout": {
                    "type": "object",
                    "description": (
                        "Optional size override, in grid units — the desktop grid is 36 columns "
                        "wide, the mobile grid is 12 columns wide (always full-width there — "
                        "mobile is effectively one column), and each row unit is a fixed 24px "
                        "tall. Default size if omitted is 12 columns wide by 9 rows tall (roughly "
                        "a third of the desktop width). Use a wider `w` for a block with a lot of "
                        "horizontal content (a table, a wide chart) and a taller `h` for a block "
                        "with a long list. Position is always auto-stacked below the existing "
                        "blocks regardless of size."
                    ),
                    "properties": {
                        "w": {"type": "integer", "description": "Width in grid columns, 1-36"},
                        "h": {"type": "integer", "description": "Height in grid rows (24px each)"},
                    },
                },
            },
            "required": ["dashboard_id", "type", "config"],
        },
    },
    {
        "name": "update_dashboard_block",
        "description": "Replace one existing block's config, and optionally its position and/or size — position, size, card background, and header visibility are all yours to set here, not just the block's own data fields. Requires contribute or edit access. Fails if the dashboard uses a template. Call get_dashboard first if you're moving or resizing — it returns every block's current {x, y, w, h} on the desktop grid so you can pick a spot that doesn't land on top of another block. Nothing here checks for overlaps automatically; read the current layout and reason about it yourself, the same way a person dragging a block on screen can see what's already there.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "string"},
                "block_id": {"type": "string"},
                "config": {
                    "type": "object",
                    "description": (
                        "Config keys per get_dashboard_block_catalog's config_fields for this "
                        "type — REPLACES the block's entire current config, so re-send every key "
                        "you want kept, not just the ones you're changing (get_dashboard returns "
                        "the block's current config to start from). Every non-chromeless block "
                        "type accepts two extra booleans here regardless of its own data fields: "
                        "`show_card` (the card/border background) and `show_header` (the icon+label "
                        "header, when the dashboard isn't in edit mode) — both default to true when "
                        "omitted, so only send one to turn it off."
                    ),
                },
                "layout": {
                    "type": "object",
                    "description": (
                        "Optional position/size override, in grid units (36-column desktop "
                        "grid, 24px rows — see get_dashboard's `grid` field and each block's "
                        "own `layout`). Omit any key to leave that aspect of the block's "
                        "current layout untouched. `x`/`y` move it (top-left corner); `w`/`h` "
                        "resize it. Only the desktop layout is affected — mobile always stays "
                        "full-width and keeps its own stacking order regardless."
                    ),
                    "properties": {
                        "x": {
                            "type": "integer",
                            "description": "Left edge, in grid columns from 0",
                        },
                        "y": {"type": "integer", "description": "Top edge, in grid rows from 0"},
                        "w": {"type": "integer", "description": "Width in grid columns, 1-36"},
                        "h": {"type": "integer", "description": "Height in grid rows (24px each)"},
                    },
                },
            },
            "required": ["dashboard_id", "block_id", "config"],
        },
    },
    {
        "name": "remove_dashboard_block",
        "description": "Remove one block from a dashboard. Requires contribute or edit access. Fails if the dashboard uses a template.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "string"},
                "block_id": {"type": "string"},
            },
            "required": ["dashboard_id", "block_id"],
        },
    },
    {
        "name": "create_dashboard_template",
        "description": (
            "Create a dashboard template — a reusable block set that every dashboard built from it stays "
            "synced to (editing the template later updates all of them automatically). owner='me' creates "
            "a personal template (any user); owner='global' creates an instance-wide template (admin only). "
            "IMPORTANT: before creating a 'global' template, tell the user in your own words that this is an "
            "instance-wide shared object — every dashboard built from it updates immediately, including ones "
            "they can't see the contents of, and there's no automatic undo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "icon": {"type": "string", "description": "Optional emoji"},
                "subject_type": {
                    "type": "string",
                    "enum": ["contact", "asset"],
                    "description": "Optional — if set, every dashboard from this template picks one contact/asset as its subject",
                },
                "blocks": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": 'List of {type, config} — call get_dashboard_block_catalog for valid types/config shapes. A contact/asset-kind field may use the literal string "$subject" instead of a concrete id if subject_type matches, resolved per-dashboard at render time.',
                },
                "owner": {"type": "string", "enum": ["me", "global"]},
            },
            "required": ["label", "owner"],
        },
    },
    {
        "name": "update_dashboard_template",
        "description": (
            "Update a dashboard template's label, icon, subject_type, or full block list. Personal templates: "
            "owner only. Global templates: admin only. IMPORTANT: before updating a GLOBAL template, tell the "
            "user in your own words that this changes an instance-wide shared object — every dashboard built "
            "from it updates immediately, including ones they can't see the contents of, and there's no "
            "automatic undo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "template_id": {"type": "string"},
                "label": {"type": "string"},
                "icon": {"type": "string"},
                "subject_type": {"type": "string", "enum": ["contact", "asset"]},
                "blocks": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Full replacement list of {type, config} blocks",
                },
                "restrict_roles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Global templates only — feature roles allowed to use this template (empty = everyone)",
                },
            },
            "required": ["template_id"],
        },
    },
]


_LG_COLS = 36  # DashboardGrid.jsx's COLS.lg — desktop grid width
_MAX_ROWS = 60  # generous cap (24px/row = 1440px tall) against a garbage/huge value
_MAX_Y = 500  # generous cap against a garbage/huge stacking position


def _block_layout_for_agent(block: dict) -> dict:
    """The desktop-grid position/size get_dashboard exposes to the agent
    (2026-08-15) — lg only, since that's the one breakpoint the agent can
    meaningfully reason about and control; sm always mirrors it at
    full-width, never independently interesting to read or set here."""
    lg = block.get("layout", {}).get("lg") or {}
    return {"x": lg.get("x", 0), "y": lg.get("y", 0), "w": lg.get("w", 12), "h": lg.get("h", 9)}


def _clamp_block_layout_override(override: dict, *, allow_position: bool, current_w: int) -> dict:
    """Clamp an agent-supplied {x?, y?, w?, h?} override to sane grid bounds
    (2026-08-15) — the agent can request a position/size, but never a
    nonsense one (zero/negative, wider than the desktop grid itself, or
    starting past its right edge). `allow_position` is False for
    add_dashboard_block (new blocks always auto-stack; see
    _apply_layout_override) and True for update_dashboard_block. `current_w`
    is the block's existing width, used to bound `x` when the override
    doesn't also change `w` — without it, an x-only move would wrongly clamp
    against the full grid width instead of the block's real (possibly much
    narrower) current width, pinning x to 0 for anything already narrower
    than full-width (caught by test_update_dashboard_block_can_move_position
    before this shipped)."""
    result = {}
    w = override.get("w")
    if isinstance(w, int) and not isinstance(w, bool):
        result["w"] = max(1, min(w, _LG_COLS))
    h = override.get("h")
    if isinstance(h, int) and not isinstance(h, bool):
        result["h"] = max(1, min(h, _MAX_ROWS))
    if allow_position:
        x = override.get("x")
        if isinstance(x, int) and not isinstance(x, bool):
            # Clamped against the resulting width (the override's own new w,
            # or else the block's current w) so the block can never be
            # placed hanging off the right edge.
            max_x = max(0, _LG_COLS - result.get("w", current_w))
            result["x"] = max(0, min(x, max_x))
        y = override.get("y")
        if isinstance(y, int) and not isinstance(y, bool):
            result["y"] = max(0, min(y, _MAX_Y))
    return result


def _apply_layout_override(layout: dict, override: dict, *, allow_position: bool = False) -> dict:
    """Apply a clamped {x?, y?, w?, h?} override onto a stacked_layout()-
    shaped {lg, sm} dict. Width/x only ever change on `lg` (the 36-col
    desktop grid; `sm` stays full-width at x=0, since mobile is effectively
    one column); height changes on both so the block reads the same tall on
    either breakpoint. `sm`'s own y is left untouched — mobile stacking order
    isn't something the agent has any way to reason about from the desktop
    grid it's shown, so an lg-only y change doesn't attempt to also guess a
    corresponding mobile position. Position (x/y) is only ever applied when
    allow_position=True (update_dashboard_block) — add_dashboard_block always
    auto-stacks new blocks via dashboards_service.stacked_layout()."""
    current_w = (layout.get("lg") or {}).get("w", _LG_COLS)
    clamped = _clamp_block_layout_override(
        override or {}, allow_position=allow_position, current_w=current_w
    )
    if not clamped:
        return layout
    result = {bp: dict(v) for bp, v in layout.items()}
    if "w" in clamped:
        result["lg"]["w"] = clamped["w"]
    if "h" in clamped:
        for bp in result:
            result[bp]["h"] = clamped["h"]
    if "x" in clamped:
        result["lg"]["x"] = clamped["x"]
    if "y" in clamped:
        result["lg"]["y"] = clamped["y"]
    return result


def execute(name: str, inputs: dict, user: dict, workspace: str = "personal"):
    if name == "list_dashboards":
        from services import dashboards_service

        return dashboards_service.list_visible_dashboards(
            user["name"],
            user.get("feature_role") or "member",
            user.get("role") == "admin",
            workspace,
        )

    if name == "get_dashboard":
        from services import dashboards_service

        found = dashboards_service.find_dashboard(
            user["name"],
            user.get("feature_role") or "member",
            user.get("role") == "admin",
            workspace,
            inputs["dashboard_id"],
        )
        if found is None:
            return {"error": f"Dashboard {inputs['dashboard_id']!r} not found or not accessible"}
        d = found["dashboard"]
        return {
            "id": d["id"],
            "name": d["name"],
            "icon": d["icon"],
            "template_id": d.get("template_id"),
            "access": found["access"],
            "grid": {"cols": _LG_COLS, "row_px": 24},
            "blocks": [
                {
                    "id": b["id"],
                    "type": b["type"],
                    "config": b["config"],
                    "layout": _block_layout_for_agent(b),
                }
                for b in d["blocks"]
            ],
        }

    if name == "list_dashboard_templates":
        from services import dashboard_templates_service

        return dashboard_templates_service.visible_templates(
            user["name"], user.get("role") == "admin", user.get("feature_role") or "member"
        )

    if name == "get_dashboard_block_catalog":
        from services.dashboard_blocks.agent_schemas import get_config_fields
        from services.dashboard_blocks.registry import catalog

        is_admin = user.get("role") == "admin"
        return [{**c, "config_fields": get_config_fields(c["type"])} for c in catalog(is_admin)]

    if name == "create_dashboard":
        from services import dashboards_service

        if inputs.get("pool") and user.get("role") != "admin":
            return {"error": "Admin access required to create a pool dashboard"}
        is_pool = bool(inputs.get("pool"))
        store_user = dashboards_service.pool_for(workspace) if is_pool else user["name"]
        # Pool pseudo-users always store at the "personal" ws_path base
        # regardless of which workspace they're paired with — same fix as
        # routers/dashboards.py's create endpoint (2026-08-18); this tool
        # had the identical bug.
        store_ws = "personal" if is_pool else workspace
        d = dashboards_service.create_dashboard(
            store_user,
            store_ws,
            user["name"],
            inputs["name"],
            inputs.get("icon") or "📊",
            template_id=inputs.get("template_id"),
            subject_id=inputs.get("subject_id"),
        )
        return {"id": d["id"], "name": d["name"], "icon": d["icon"]}

    if name == "add_dashboard_block":
        from services import dashboards_service
        from services.dashboard_blocks.registry import REGISTRY

        found = dashboards_service.find_dashboard(
            user["name"],
            user.get("feature_role") or "member",
            user.get("role") == "admin",
            workspace,
            inputs["dashboard_id"],
        )
        if found is None:
            return {"error": f"Dashboard {inputs['dashboard_id']!r} not found or not accessible"}
        if found["access"] not in ("edit", "contribute"):
            return {"error": "Read-only access — you cannot add blocks to this dashboard"}
        dashboard = found["dashboard"]
        if dashboard.get("template_id"):
            return {
                "error": "This dashboard's block set comes from a template — use "
                "update_dashboard_template to change its blocks, or detach it from the "
                "template first."
            }
        if inputs["type"] not in REGISTRY:
            return {
                "error": f"Unknown block type {inputs['type']!r} — call get_dashboard_block_catalog"
            }
        new_block = {
            "id": str(uuid.uuid4()),
            "type": inputs["type"],
            "config": inputs.get("config") or {},
            "layout": _apply_layout_override(
                dashboards_service.stacked_layout(dashboard["blocks"]),
                inputs.get("layout"),
            ),
        }
        updated = dashboards_service.update_dashboard(
            found["store"],
            found["store_workspace"],
            inputs["dashboard_id"],
            {"blocks": dashboard["blocks"] + [new_block]},
            by=user["name"],
        )
        return {
            "ok": True,
            "block_id": new_block["id"],
            "blocks": [
                {"id": b["id"], "type": b["type"], "config": b["config"]} for b in updated["blocks"]
            ],
        }

    if name == "update_dashboard_block":
        from services import dashboards_service

        found = dashboards_service.find_dashboard(
            user["name"],
            user.get("feature_role") or "member",
            user.get("role") == "admin",
            workspace,
            inputs["dashboard_id"],
        )
        if found is None:
            return {"error": f"Dashboard {inputs['dashboard_id']!r} not found or not accessible"}
        if found["access"] not in ("edit", "contribute"):
            return {"error": "Read-only access — you cannot update blocks on this dashboard"}
        dashboard = found["dashboard"]
        if dashboard.get("template_id"):
            return {
                "error": "This dashboard's block set comes from a template — use "
                "update_dashboard_template to change its blocks."
            }
        target = next((b for b in dashboard["blocks"] if b["id"] == inputs["block_id"]), None)
        if target is None:
            return {"error": f"Block {inputs['block_id']!r} not found on this dashboard"}
        new_layout = (
            _apply_layout_override(target["layout"], inputs["layout"], allow_position=True)
            if inputs.get("layout")
            else target["layout"]
        )
        new_blocks = [
            (
                {**b, "config": inputs["config"], "layout": new_layout}
                if b["id"] == inputs["block_id"]
                else b
            )
            for b in dashboard["blocks"]
        ]
        updated = dashboards_service.update_dashboard(
            found["store"],
            found["store_workspace"],
            inputs["dashboard_id"],
            {"blocks": new_blocks},
            by=user["name"],
        )
        return {
            "ok": True,
            "blocks": [
                {"id": b["id"], "type": b["type"], "config": b["config"]} for b in updated["blocks"]
            ],
        }

    if name == "remove_dashboard_block":
        from services import dashboards_service

        found = dashboards_service.find_dashboard(
            user["name"],
            user.get("feature_role") or "member",
            user.get("role") == "admin",
            workspace,
            inputs["dashboard_id"],
        )
        if found is None:
            return {"error": f"Dashboard {inputs['dashboard_id']!r} not found or not accessible"}
        if found["access"] not in ("edit", "contribute"):
            return {"error": "Read-only access — you cannot remove blocks from this dashboard"}
        dashboard = found["dashboard"]
        if dashboard.get("template_id"):
            return {
                "error": "This dashboard's block set comes from a template — use "
                "update_dashboard_template to change its blocks."
            }
        if not any(b["id"] == inputs["block_id"] for b in dashboard["blocks"]):
            return {"error": f"Block {inputs['block_id']!r} not found on this dashboard"}
        new_blocks = [b for b in dashboard["blocks"] if b["id"] != inputs["block_id"]]
        updated = dashboards_service.update_dashboard(
            found["store"],
            found["store_workspace"],
            inputs["dashboard_id"],
            {"blocks": new_blocks},
            by=user["name"],
        )
        return {
            "ok": True,
            "blocks": [
                {"id": b["id"], "type": b["type"], "config": b["config"]} for b in updated["blocks"]
            ],
        }

    if name == "create_dashboard_template":
        from services import dashboard_templates_service

        owner_param = inputs.get("owner", "me")
        if owner_param == "global" and user.get("role") != "admin":
            return {"error": "Admin access required to create a global template"}
        owner = (
            dashboard_templates_service.GLOBAL_OWNER if owner_param == "global" else user["name"]
        )
        return dashboard_templates_service.create_template(
            {
                "label": inputs.get("label"),
                "icon": inputs.get("icon"),
                "subject_type": inputs.get("subject_type"),
                "blocks": inputs.get("blocks") or [],
            },
            owner=owner,
        )

    if name == "update_dashboard_template":
        from services import dashboard_templates_service

        found = dashboard_templates_service._find_template(inputs["template_id"])
        if found is None:
            return {"error": f"Template {inputs['template_id']!r} not found"}
        owner, _tmpl = found
        is_global = owner == dashboard_templates_service.GLOBAL_OWNER
        if is_global and user.get("role") != "admin":
            return {"error": "Admin access required to update a global template"}
        if not is_global and owner != user["name"]:
            return {"error": "You can only update your own personal templates"}
        updates = {k: v for k, v in inputs.items() if k != "template_id"}
        result = dashboard_templates_service.update_template(inputs["template_id"], updates)
        return result or {"error": f"Template {inputs['template_id']!r} not found"}

    return None
