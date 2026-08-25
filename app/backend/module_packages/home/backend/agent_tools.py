"""AI agent tools owned by the home module — TOOL_SCHEMAS is folded into
_get_tools()'s returned list (filtered by disabled_modules, then further
filtered to only appear once Home Assistant is actually configured — see
agent_service.py's _get_tools(), which keeps that ha_ok check itself since
it applies regardless of which list a tool's schema came from), and
execute() is what agent_service.py's tool executor falls back to for any
name its own core match/case doesn't handle. Returning None means "not one
of mine" so the dispatcher can try the next module.

get_home_state is deliberately NOT in this module's read_only_agent_tools —
it's read-only (safe without approval in approve mode) but excluded from
research mode specifically, a distinction agent_service.py's hardcoded
_READ_TOOLS = _RESEARCH_TOOLS | {"get_home_state", "ask_user_question"} line
still carries directly by name, unchanged by this module's conversion (see
docs/MEMORY.md 2026-08-24, Home conversion entry)."""

from services import ha_service

TOOL_SCHEMAS = [
    {
        "name": "get_home_state",
        "description": (
            "Get the current state of one or more Home Assistant entities (lights, sensors, thermostats, locks, etc.). "
            "Only available when Home Assistant is configured."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of entity_ids, e.g. ['light.living_room', 'sensor.temperature']",
                },
            },
            "required": ["entity_ids"],
        },
    },
    {
        "name": "control_home_device",
        "description": (
            "Control a Home Assistant device. Use domain/service per HA docs "
            "(e.g. light/turn_on, switch/turn_off, climate/set_temperature). "
            "Only available when Home Assistant is configured."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "HA entity_id to control"},
                "domain": {
                    "type": "string",
                    "description": "HA service domain, e.g. 'light', 'switch', 'climate'",
                },
                "service": {
                    "type": "string",
                    "description": "HA service name, e.g. 'turn_on', 'turn_off', 'set_temperature'",
                },
                "data": {
                    "type": "object",
                    "description": "Optional service data, e.g. {brightness_pct: 80, temperature: 72}",
                },
            },
            "required": ["entity_id", "domain", "service"],
        },
    },
    {
        "name": "activate_scene",
        "description": "Activate a Home Assistant scene by its entity_id. Only available when Home Assistant is configured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Scene entity_id, e.g. 'scene.movie_time'",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "trigger_home_automation",
        "description": "Trigger a Home Assistant automation by its entity_id. Only available when Home Assistant is configured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Automation entity_id, e.g. 'automation.morning_routine'",
                },
            },
            "required": ["entity_id"],
        },
    },
]


def execute(name: str, inputs: dict, user: dict):
    if name == "get_home_state":
        return [ha_service.get_state(eid) for eid in inputs["entity_ids"]]

    if name == "control_home_device":
        data = dict(inputs.get("data") or {})
        data["entity_id"] = inputs["entity_id"]
        return ha_service.call_service(inputs["domain"], inputs["service"], data)

    if name == "activate_scene":
        return ha_service.call_service("scene", "turn_on", {"entity_id": inputs["entity_id"]})

    if name == "trigger_home_automation":
        return ha_service.trigger_automation(inputs["entity_id"])

    return None
