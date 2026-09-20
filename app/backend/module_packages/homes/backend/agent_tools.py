"""AI agent tools owned by the homes module. Deliberately personal-scope
only (mirrors goals'/tasks'/notes' own precedent) — pool home management
isn't exposed to the AI in this pass, same reasoning Goals' own
agent_tools.py already documents."""

from module_packages.homes.backend import service as homes_service

TOOL_SCHEMAS = [
    {
        "name": "list_homes",
        "description": "List all of the user's homes. Each has an id, name, tag, ownership_type (rent or own), and address.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_home",
        "description": "Get one home's full detail, including its rent or own fields and its tag (apply that tag to a task/note/event/transaction elsewhere to associate it with this home).",
        "input_schema": {
            "type": "object",
            "properties": {
                "home_id": {"type": "string", "description": "Home ID"},
            },
            "required": ["home_id"],
        },
    },
    {
        "name": "create_home",
        "description": "Create a new home (rented or owned). A tag is generated automatically — tell the user what it is so they can apply it elsewhere.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "ownership_type": {"type": "string", "enum": ["rent", "own"]},
                "address": {"type": "string"},
                "notes": {"type": "string"},
                "rent": {
                    "type": "object",
                    "description": "Only used when ownership_type is 'rent': landlord_name, monthly_rent, lease_start, lease_end, security_deposit",
                },
                "own": {
                    "type": "object",
                    "description": "Only used when ownership_type is 'own': lender_name, monthly_payment, purchase_date, purchase_price, property_tax_annual",
                },
            },
            "required": ["name", "ownership_type"],
        },
    },
    {
        "name": "update_home",
        "description": "Update an existing home by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "home_id": {"type": "string"},
                "name": {"type": "string"},
                "ownership_type": {"type": "string", "enum": ["rent", "own"]},
                "address": {"type": "string"},
                "notes": {"type": "string"},
                "rent": {"type": "object"},
                "own": {"type": "object"},
            },
            "required": ["home_id"],
        },
    },
    {
        "name": "delete_home",
        "description": "Delete a home (moved to Trash, recoverable for 30 days). Tagged items elsewhere are never touched.",
        "input_schema": {
            "type": "object",
            "properties": {
                "home_id": {"type": "string"},
            },
            "required": ["home_id"],
        },
    },
]


def execute(name: str, inputs: dict, user: dict, workspace: str = "personal"):
    if name == "list_homes":
        return homes_service.list_homes(user["name"], workspace)

    if name == "get_home":
        home = homes_service.get_home(user["name"], inputs["home_id"], workspace)
        if home is None:
            return {"error": f"Home {inputs['home_id']!r} not found"}
        return home

    if name == "create_home":
        payload = {k: v for k, v in inputs.items()}
        payload["created_by"] = user["name"]
        try:
            return homes_service.create_home(user["name"], payload, workspace)
        except ValueError as exc:
            return {"error": str(exc)}

    if name == "update_home":
        home_id = inputs["home_id"]
        updates = {k: v for k, v in inputs.items() if k != "home_id"}
        try:
            result = homes_service.update_home(user["name"], home_id, updates, workspace)
        except ValueError as exc:
            return {"error": str(exc)}
        if result is None:
            return {"error": f"Home {home_id!r} not found"}
        return result

    if name == "delete_home":
        if not homes_service.delete_home(
            user["name"], inputs["home_id"], workspace, deleted_by=user["name"]
        ):
            return {"error": f"Home {inputs['home_id']!r} not found"}
        return {"deleted": True}

    return None
