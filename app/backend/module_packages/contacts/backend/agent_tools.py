"""AI agent tools owned by the contacts module — TOOL_SCHEMAS is folded into
_get_tools()'s returned list (filtered by disabled_modules first, then
list_contacts/get_contact additionally feed research_tools/_READ_TOOLS via
the manifest's read_only_agent_tools). execute() is what agent_service.py's
tool executor falls back to for any name its own core match/case doesn't
handle. Returning None means "not one of mine" so the dispatcher can try
the next module.

get_profile/update_profile stay core (agent_service.py's own case
statements), not here — Profile is a generic concept independent of
Contacts' module state (the self-contact mechanism is deliberately
reachable regardless of whether Contacts is installed, matching
GET/PATCH /contacts/me's own module-gate-free design), even though both
tools call contacts_service internally. contacts_service itself stays core
regardless either way."""

TOOL_SCHEMAS = [
    {
        "name": "list_contacts",
        "description": (
            "List CRM contacts visible in the active workspace (own + shared + pool). "
            "Use `query` to search by name/email/tag. Returns id, name, type, emails, tags, status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "get_contact",
        "description": "Get one contact's full detail plus its interactions and deals, by contact id.",
        "input_schema": {
            "type": "object",
            "properties": {"contact_id": {"type": "string"}},
            "required": ["contact_id"],
        },
    },
    {
        "name": "create_contact",
        "description": (
            "Create a CRM contact. ALWAYS check for an existing match first — this tool "
            "auto-searches by name/email and returns the existing contact instead of creating a "
            "duplicate. Provide name (required), optional type (person|company), emails, phones, tags, notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": ["person", "company"]},
                "emails": {"type": "array", "items": {"type": "string"}},
                "phones": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "update_contact",
        "description": "Update fields on an existing contact by id (name, emails, phones, tags, status, notes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "fields": {"type": "object"},
            },
            "required": ["contact_id", "fields"],
        },
    },
    {
        "name": "log_interaction",
        "description": (
            "Log an interaction with a contact (call/email/meeting/text/note) with a summary and "
            "optional follow_up date (YYYY-MM-DD)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "type": {"type": "string", "enum": ["call", "email", "meeting", "text", "note"]},
                "summary": {"type": "string"},
                "follow_up": {"type": "string"},
            },
            "required": ["contact_id", "summary"],
        },
    },
    {
        "name": "create_deal",
        "description": "Create a deal on a contact: title (required), value_cents, and pipeline stage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "title": {"type": "string"},
                "value_cents": {"type": "integer"},
                "stage": {"type": "string"},
            },
            "required": ["contact_id", "title"],
        },
    },
]


def execute(name: str, inputs: dict, user: dict, workspace: str = "personal"):
    if name == "list_contacts":
        from services import contacts_service

        out = contacts_service.list_visible_contacts(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
        )
        q = (inputs.get("query") or "").strip().lower()
        if q:
            out = [
                c
                for c in out
                if q in c.get("name", "").lower()
                or any(q in e.lower() for e in c.get("emails", []))
                or any(q in t.lower() for t in c.get("tags", []))
            ]
        return [
            {
                "id": c["id"],
                "name": c.get("name"),
                "type": c.get("type"),
                "emails": c.get("emails", []),
                "tags": c.get("tags", []),
                "status": c.get("status", ""),
            }
            for c in out[:100]
        ]

    if name == "get_contact":
        from services import contacts_service

        found = contacts_service.find_contact(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["contact_id"],
        )
        if not found:
            return {"error": "Contact not found"}
        store_user, contact, _access = found
        ws = contacts_service.effective_workspace(store_user, contact, workspace)
        return {
            "contact": contact,
            "interactions": contacts_service.list_interactions(store_user, ws, contact["id"]),
            "deals": contacts_service.list_deals(store_user, ws, contact["id"]),
        }

    if name == "create_contact":
        from services import contacts_service

        email = (inputs.get("emails") or [""])[0] if inputs.get("emails") else ""
        existing = contacts_service.find_match(
            user["name"], workspace, name=inputs.get("name", ""), email=email
        )
        if existing:
            return {
                "existing": True,
                "contact_id": existing["id"],
                "message": f"A contact named {existing['name']} already exists — reusing it.",
            }
        contact = contacts_service.create_contact(
            user["name"], workspace, inputs, created_by=user["name"]
        )
        return {"created": True, "contact_id": contact["id"]}

    if name == "update_contact":
        from services import contacts_service

        found = contacts_service.find_contact(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["contact_id"],
        )
        if not found:
            return {"error": "Contact not found"}
        store_user, contact, access = found
        if access != "edit":
            return {"error": "You don't have edit access to this contact"}
        ws = contacts_service.effective_workspace(store_user, contact, workspace)
        updated = contacts_service.update_contact(
            store_user,
            ws,
            inputs["contact_id"],
            inputs.get("fields", {}),
            viewer=user["name"],
        )
        return {"updated": bool(updated)}

    if name == "log_interaction":
        from services import contacts_service

        found = contacts_service.find_contact(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["contact_id"],
        )
        if not found:
            return {"error": "Contact not found"}
        store_user, contact, access = found
        if access not in ("edit", "contribute"):
            return {"error": "You don't have access to add to this contact"}
        ws = contacts_service.effective_workspace(store_user, contact, workspace)
        item = contacts_service.add_interaction(
            store_user, ws, inputs["contact_id"], inputs, created_by=user["name"]
        )
        return {"logged": True, "interaction_id": item["id"]}

    if name == "create_deal":
        from services import contacts_service

        found = contacts_service.find_contact(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            inputs["contact_id"],
        )
        if not found:
            return {"error": "Contact not found"}
        store_user, contact, access = found
        if access not in ("edit", "contribute"):
            return {"error": "You don't have access to add to this contact"}
        ws = contacts_service.effective_workspace(store_user, contact, workspace)
        deal = contacts_service.add_deal(
            store_user, ws, inputs["contact_id"], inputs, created_by=user["name"]
        )
        return {"created": True, "deal_id": deal["id"]}

    return None
