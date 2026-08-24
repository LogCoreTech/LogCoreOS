"""AI agent tools owned by the journal module — TOOL_SCHEMAS is folded into
_get_tools()'s returned list (filtered by disabled_modules first), and
execute() is what agent_service.py's tool executor falls back to for any
name its own core match/case doesn't handle. Returning None means "not one
of mine" so the dispatcher can try the next module."""

from module_packages.journal.backend import service as journal_service

TOOL_SCHEMAS = [
    {
        "name": "read_journal_entry",
        "description": "Read the user's journal entry for a specific date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            },
            "required": ["date"],
        },
    },
    {
        "name": "write_journal_entry",
        "description": "Create or update the user's journal entry for a specific date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "content": {"type": "string", "description": "Full markdown content of the entry"},
            },
            "required": ["date", "content"],
        },
    },
    {
        "name": "list_journal_entries",
        "description": "List journal entries with their full content, optionally filtered by date range. Useful for progress summaries and reflection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "since": {
                    "type": "string",
                    "description": "Only return entries on or after this date (YYYY-MM-DD)",
                },
                "until": {
                    "type": "string",
                    "description": "Only return entries on or before this date (YYYY-MM-DD)",
                },
                "limit": {"type": "integer", "description": "Max entries to return (default 7)"},
            },
            "required": [],
        },
    },
]


def execute(name: str, inputs: dict, user: dict):
    if name == "read_journal_entry":
        entry = journal_service.get_entry(user["name"], inputs["date"])
        if entry is None:
            return {"date": inputs["date"], "content": "", "exists": False}
        return {**entry, "exists": True}

    if name == "write_journal_entry":
        return journal_service.upsert_entry(user["name"], inputs["date"], inputs["content"])

    if name == "list_journal_entries":
        since = inputs.get("since")
        until = inputs.get("until")
        limit = int(inputs.get("limit", 7))
        entries = journal_service.list_entries(user["name"])
        if since:
            entries = [e for e in entries if e["date"] >= since]
        if until:
            entries = [e for e in entries if e["date"] <= until]
        result = []
        for e in entries[:limit]:
            full = journal_service.get_entry(user["name"], e["date"])
            if full:
                result.append({"date": e["date"], "content": full.get("content", "")})
        return result

    return None
