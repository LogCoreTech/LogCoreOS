"""AI agent tools owned by the notes module — TOOL_SCHEMAS is folded into
_get_tools()'s returned list (filtered by disabled_modules first, then
list_notes/read_note additionally feed research_tools/_READ_TOOLS via the
manifest's read_only_agent_tools), and execute() is what agent_service.py's
tool executor falls back to for any name its own core match/case doesn't
handle. Returning None means "not one of mine" so the dispatcher can try
the next module.

Notes is the first module whose AI tools genuinely need the caller's active
workspace (a note lives in either the personal or business Notes/ folder,
same as the note itself) — the generic dispatch call site
(_execute_tool's `case _:` in agent_service.py) only ever passed
(name, inputs, user), a real, previously-harmless gap Tasks' own move
already hit and explicitly left unfixed (its own agent_tools.py docstring:
"not a regression introduced by this move; not fixed here either"), since
Tasks' tools never used workspace even inline. Notes' tools DID use it
inline (every notes_service call below took workspace as a real argument
before this move) — silently dropping it here would have been an actual
regression, not a no-op, so the dispatch signature was widened to
execute(name, inputs, user, workspace) instead, with every other module's
own execute() picking up the new parameter (default "personal", unused) for
signature parity. See docs/MEMORY.md's 2026-08-26 entry for the full
reasoning.

search_brain is NOT a notes tool (it also rglobs journal/memory/profile
files) — it stays in agent_service.py, unmoved, same as before."""

from services import notes_service

TOOL_SCHEMAS = [
    {
        "name": "list_notes",
        "description": (
            "List all notes and folders visible to the user: their own, the household/team pool's, "
            "and any shared with them by another user. A note from someone else carries an `_owner` "
            "field (a username, or 'household'/'team' for a pool note) and an `_access` field "
            "(read|contribute|edit) — own notes have neither. Pass the `_owner` you got back here into "
            "read_note/update_note/delete_note/move_note's own `owner` param so they resolve to the "
            "right store even if the same note name exists in more than one place."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_note",
        "description": "Read an existing note's content, including one shared with the user or in the household/team pool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative note path, e.g. 'Work/Meeting Notes'",
                },
                "owner": {
                    "type": "string",
                    "description": "Optional — the note's `_owner` field from list_notes, if it has one. Disambiguates when the same path could exist in more than one visible store.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "create_note",
        "description": "Create a new note in the user's own Notes folder. Path is relative to Notes/ without the .md extension, e.g. 'Work/Meeting Notes' or 'Ideas'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative note path, e.g. 'Work/Meeting Notes'",
                },
                "content": {
                    "type": "string",
                    "description": "Initial markdown content (defaults to empty)",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "update_note",
        "description": (
            "Overwrite an existing note's content — the user's own, or one shared with them at "
            "contribute/edit level. Use list_notes or read_note first if you need to see what's there."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative note path, e.g. 'Work/Meeting Notes'",
                },
                "content": {"type": "string", "description": "New full markdown content"},
                "owner": {
                    "type": "string",
                    "description": "Optional — the note's `_owner` field from list_notes, if it has one. Disambiguates when the same path could exist in more than one visible store.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "delete_note",
        "description": "Permanently delete a note by path — the user's own, or one shared with them at edit level.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative note path, e.g. 'Work/Meeting Notes'",
                },
                "owner": {
                    "type": "string",
                    "description": "Optional — the note's `_owner` field from list_notes, if it has one. Disambiguates when the same path could exist in more than one visible store.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "move_note",
        "description": "Move or rename a note — the user's own, or one shared with them at edit level. Paths are relative to Notes/ without .md extension.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_path": {"type": "string", "description": "Current note path, e.g. 'Ideas'"},
                "to_path": {
                    "type": "string",
                    "description": "New note path, e.g. 'Brainstorms/Ideas'",
                },
                "owner": {
                    "type": "string",
                    "description": "Optional — the note's `_owner` field from list_notes, if it has one. Disambiguates when the same path could exist in more than one visible store.",
                },
            },
            "required": ["from_path", "to_path"],
        },
    },
    {
        "name": "create_note_folder",
        "description": "Create a folder inside the user's Notes directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Folder path relative to Notes/, e.g. 'Projects' or 'Projects/Work'",
                },
            },
            "required": ["path"],
        },
    },
]


def _resolve_note_or_error(user: dict, workspace: str, path: str, owner: str | None, need: str):
    """Resolve a note/folder path the agent's caller can reach at >= `need`
    access, the same way routers/notes.py's own _resolve() does for real
    users. Returns (store_user, None) on success or (None, error_dict)."""
    try:
        found = notes_service.find_note_store(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
            path,
            owner=owner,
        )
    except ValueError as e:
        return None, {"error": str(e)}
    if not found:
        return None, {"error": f"Note not found: {path!r}"}
    store_user, access = found
    if not notes_service.meets(access, need):
        return None, {"error": f"You only have {access} access to {path!r} — that's not enough."}
    return store_user, None


def execute(name: str, inputs: dict, user: dict, workspace: str = "personal"):
    if name == "list_notes":
        return notes_service.list_visible_notes(
            user["name"],
            user.get("feature_role", "member"),
            user.get("role") == "admin",
            workspace,
        )

    if name == "read_note":
        store_user, err = _resolve_note_or_error(
            user, workspace, inputs["path"], inputs.get("owner"), "read"
        )
        if err:
            return err
        note = notes_service.get_note(store_user, inputs["path"], workspace)
        return note or {"error": f"Note not found: {inputs['path']!r}"}

    if name == "create_note":
        return notes_service.create_note(
            user["name"], inputs["path"], inputs.get("content", ""), workspace
        )

    if name == "update_note":
        store_user, err = _resolve_note_or_error(
            user, workspace, inputs["path"], inputs.get("owner"), "contribute"
        )
        if err:
            return err
        result = notes_service.update_note(store_user, inputs["path"], inputs["content"], workspace)
        return result or {"error": f"Note not found: {inputs['path']!r}"}

    if name == "delete_note":
        store_user, err = _resolve_note_or_error(
            user, workspace, inputs["path"], inputs.get("owner"), "edit"
        )
        if err:
            return err
        ok = notes_service.delete_note(store_user, inputs["path"], workspace)
        return {"deleted": ok}

    if name == "move_note":
        store_user, err = _resolve_note_or_error(
            user, workspace, inputs["from_path"], inputs.get("owner"), "edit"
        )
        if err:
            return err
        return notes_service.move_item(
            store_user, inputs["from_path"], inputs["to_path"], "note", workspace
        )

    if name == "create_note_folder":
        return notes_service.create_folder(user["name"], inputs["path"], workspace)

    return None
