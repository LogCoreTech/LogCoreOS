"""AI agent tools owned by the assets module — TOOL_SCHEMAS is folded into
_get_tools()'s returned list (filtered by disabled_modules first, then
list_asset_templates/list_assets/search_assets additionally feed
research_tools/_READ_TOOLS via the manifest's read_only_agent_tools, and
delete_asset/create_asset_template/update_asset_template are also listed
in the manifest's admin_agent_tools so their SCHEMAS are only ever offered
to admin callers in the first place — same mechanism Household's own
shared-task tools already use). execute() is what agent_service.py's tool
executor falls back to for any name its own core match/case doesn't
handle. Returning None means "not one of mine" so the dispatcher can try
the next module.

All 10 tools were already correctly workspace-threaded inline before this
move (every non-template tool resolves through find_asset()/list_visible(),
the sharing-aware entry points) — the generic dispatch signature
(execute(name, inputs, user, workspace), widened during notes/'s own
conversion) already covers everything here, no further mechanism change
needed, just the relocation. The 3 admin-only tools keep their own inline
`if user.get("role") != "admin"` execution check unchanged — admin_agent_tools
only controls whether their SCHEMAS are shown to a non-admin caller, not
this runtime check, matching Household's own precedent exactly."""

TOOL_SCHEMAS = [
    {
        "name": "list_asset_templates",
        "description": "List asset templates (the premade field structures, e.g. 'parcel'). Call this BEFORE creating or updating assets to learn valid template keys and field keys/types/options.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_assets",
        "description": "List assets visible to the user in the current workspace: their own, pool (team/household) assets, and assets shared with them. Assets form a tree via parent_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "template": {"type": "string", "description": "Filter by template key"},
                "include_archived": {"type": "boolean", "description": "Include archived assets"},
            },
            "required": [],
        },
    },
    {
        "name": "create_asset",
        "description": "Create an asset in the user's own store. Call list_asset_templates first — 'fields' keys must match the template's field keys exactly.",
        "input_schema": {
            "type": "object",
            "properties": {
                "template": {"type": "string", "description": "Template key, e.g. 'parcel'"},
                "name": {"type": "string", "description": "Asset name, e.g. 'Lot 12'"},
                "parent_id": {
                    "type": "string",
                    "description": "Optional parent asset ID for nesting",
                },
                "fields": {
                    "type": "object",
                    "description": "Field values keyed by the template's field keys",
                },
                "notes": {"type": "string"},
            },
            "required": ["template", "name"],
        },
    },
    {
        "name": "update_asset",
        "description": "Update an asset's name, notes, or field values by ID. Respects the user's access (read-only shares cannot be updated).",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "name": {"type": "string"},
                "fields": {
                    "type": "object",
                    "description": "Field values to merge; null deletes a key",
                },
                "notes": {"type": "string"},
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "archive_asset",
        "description": "Archive (or unarchive) an asset. Archiving hides the asset and its whole subtree from default views without deleting anything.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "archived": {
                    "type": "boolean",
                    "description": "true to archive (default), false to unarchive",
                },
                "cascade": {
                    "type": "boolean",
                    "description": "true to also (un)archive all descendants",
                },
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "search_assets",
        "description": "Search the assets visible to the user by a text query — matches asset name and field values. Use this instead of list_assets when looking for specific assets in a large collection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to match in name or field values"},
                "template": {"type": "string", "description": "Optional template key filter"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "move_asset",
        "description": "Move an asset to a new parent (or to the top level with parent_id null). Same owner only. Respects the user's edit access.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "parent_id": {
                    "type": "string",
                    "description": "New parent asset ID, or null for top level",
                },
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "delete_asset",
        "description": "Permanently delete an asset by ID (admin only). Fails if the asset has children. Prefer archive_asset unless the user explicitly wants permanent deletion.",
        "input_schema": {
            "type": "object",
            "properties": {"asset_id": {"type": "string"}},
            "required": ["asset_id"],
        },
    },
    {
        "name": "create_asset_template",
        "description": "Create an asset template (admin only). Fields are an ordered list of {key, label, type, options?, default?}; types: text, number, date, boolean, select.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Slug key, e.g. 'parcel' (immutable)"},
                "label": {"type": "string"},
                "icon": {"type": "string", "description": "Optional emoji"},
                "fields": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Ordered field definitions: {key, label, type, options?, default?}",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "update_asset_template",
        "description": "Update an asset template's label, icon, or full field list (admin only). The key is immutable. Changing fields affects every asset using this template — confirm with the user first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "label": {"type": "string"},
                "icon": {"type": "string"},
                "fields": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Full replacement list of field definitions",
                },
            },
            "required": ["key"],
        },
    },
]


def execute(name: str, inputs: dict, user: dict, workspace: str = "personal"):
    if name == "list_asset_templates":
        from services import assets_service

        return assets_service.visible_templates(
            user["name"],
            is_admin=user.get("role") == "admin",
            feature_role=user.get("feature_role", "member"),
        )

    if name == "list_assets":
        from services import assets_service

        items = assets_service.list_visible(
            user["name"],
            workspace,
            include_archived=bool(inputs.get("include_archived")),
            is_admin=user.get("role") == "admin",
            pool_edit=user.get("pool_edit") or [],
            viewer_role=user.get("feature_role") or "",
        )
        if inputs.get("template"):
            items = [a for a in items if a.get("template") == inputs["template"]]
        # History is noise for the model — drop it from tool output
        return [{k: v for k, v in a.items() if k != "history"} for a in items]

    if name == "create_asset":
        from services import assets_service

        return assets_service.create_asset(
            user["name"], inputs, workspace=workspace, created_by=user["name"]
        )

    if name == "update_asset":
        from services import assets_service

        found = assets_service.find_asset(
            user["name"],
            workspace,
            inputs["asset_id"],
            is_admin=user.get("role") == "admin",
            pool_edit=user.get("pool_edit") or [],
            viewer_role=user.get("feature_role") or "",
        )
        if found is None:
            return {"error": f"Asset {inputs['asset_id']!r} not found"}
        if not found["can_edit"]:
            return {"error": "Read-only access — you cannot update this asset"}
        updates = {k: v for k, v in inputs.items() if k != "asset_id"}
        result = assets_service.update_asset(
            found["store"],
            inputs["asset_id"],
            updates,
            workspace=found["store_workspace"],
            by=user["name"],
        )
        return result or {"error": "Asset not found"}

    if name == "archive_asset":
        from services import assets_service

        found = assets_service.find_asset(
            user["name"],
            workspace,
            inputs["asset_id"],
            is_admin=user.get("role") == "admin",
            pool_edit=user.get("pool_edit") or [],
            viewer_role=user.get("feature_role") or "",
        )
        if found is None:
            return {"error": f"Asset {inputs['asset_id']!r} not found"}
        if not found["can_manage"]:
            return {"error": "Only the owner or a pool manager can archive this asset"}
        result = assets_service.set_archived(
            found["store"],
            inputs["asset_id"],
            bool(inputs.get("archived", True)),
            workspace=found["store_workspace"],
            by=user["name"],
            cascade=bool(inputs.get("cascade", False)),
        )
        return result or {"error": "Asset not found"}

    if name == "search_assets":
        from services import assets_service

        items = assets_service.list_visible(
            user["name"],
            workspace,
            is_admin=user.get("role") == "admin",
            pool_edit=user.get("pool_edit") or [],
            viewer_role=user.get("feature_role") or "",
        )
        if inputs.get("template"):
            items = [a for a in items if a.get("template") == inputs["template"]]
        q = str(inputs.get("query", "")).strip().lower()
        if q:

            def _match(a: dict) -> bool:
                if q in (a.get("name") or "").lower():
                    return True
                return any(q in str(v).lower() for v in (a.get("fields") or {}).values())

            items = [a for a in items if _match(a)]
        return [{k: v for k, v in a.items() if k != "history"} for a in items]

    if name == "move_asset":
        from services import assets_service

        found = assets_service.find_asset(
            user["name"],
            workspace,
            inputs["asset_id"],
            is_admin=user.get("role") == "admin",
            pool_edit=user.get("pool_edit") or [],
            viewer_role=user.get("feature_role") or "",
        )
        if found is None:
            return {"error": f"Asset {inputs['asset_id']!r} not found"}
        if not found["can_edit"]:
            return {"error": "Read-only access — you cannot move this asset"}
        result = assets_service.update_asset(
            found["store"],
            inputs["asset_id"],
            {"parent_id": inputs.get("parent_id")},
            workspace=found["store_workspace"],
            by=user["name"],
        )
        return result or {"error": "Asset not found"}

    if name == "delete_asset":
        from services import assets_service

        if user.get("role") != "admin":
            return {"error": "Admin access required"}
        found = assets_service.find_asset(user["name"], workspace, inputs["asset_id"], is_admin=True)
        if found is None:
            return {"error": f"Asset {inputs['asset_id']!r} not found"}
        ok = assets_service.delete_asset(
            found["store"], inputs["asset_id"], workspace=found["store_workspace"]
        )
        return {"deleted": ok}

    if name == "create_asset_template":
        from services import assets_service

        if user.get("role") != "admin":
            return {"error": "Admin access required"}
        # Admin chat manages GLOBAL templates.
        return assets_service.create_template(inputs, owner=assets_service.GLOBAL_OWNER)

    if name == "update_asset_template":
        from services import assets_service

        if user.get("role") != "admin":
            return {"error": "Admin access required"}
        tmpl = assets_service.get_global_template(inputs["key"])
        if tmpl is None:
            return {"error": f"Global template {inputs['key']!r} not found"}
        updates = {k: v for k, v in inputs.items() if k != "key"}
        result = assets_service.update_template(tmpl["id"], updates)
        return result or {"error": f"Template {inputs['key']!r} not found"}

    return None
