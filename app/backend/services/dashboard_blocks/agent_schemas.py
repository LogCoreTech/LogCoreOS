"""Agent-facing mirror of app/frontend/src/components/dashboard/blockRegistry.js's
CONFIG_FIELD_SCHEMAS — a maintained port, same convention as this package's own
registry.py/blockRegistry.js split (backend is the source of truth for GATING,
frontend owns rendering; here the frontend is the source of truth for what a
block's config fields ARE, since that's authored once for the picker UI and
must not drift from what a human sees when they open the same block to edit
it by hand). Key names intentionally match the JS shape (dependsOn/showIf,
not snake_case) so the two files stay visually diffable against each other.

The one real translation, not just a copy: `nav_button`'s `moduleAndRecord`
kind is a single composite UI picker in the frontend (one control choosing
three things at once) but sets three independent flat config keys under the
hood (module/record_id/section) — there is no equivalent composite widget for
an agent to "click," so it gets those three keys directly instead of a kind
the agent can't act on.

Every other kind here names a plain id/value the agent is expected to already
have or look up via its own read tools (e.g. call list_tasks to find a task's
id for a `task`-kind field) — this module describes what each field MEANS,
it does not render anything.
"""

AGENT_CONFIG_SCHEMAS: dict[str, list[dict]] = {
    "single_task": [
        {"key": "task_id", "label": "Task id (look it up via list_tasks)", "kind": "task"}
    ],
    "finance_activity": [
        {"key": "asset_id", "label": "Asset id", "kind": "asset", "optional": True},
        {"key": "contact_id", "label": "Contact id", "kind": "contact", "optional": True},
        {"key": "book_id", "label": "Finance book id", "kind": "financeBook", "optional": True},
    ],
    "finance_book_report": [{"key": "book_id", "label": "Finance book id", "kind": "financeBook"}],
    "linked_deals": [{"key": "contact_id", "label": "Contact id", "kind": "contact"}],
    "custom_fields": [
        {"key": "contact_id", "label": "Contact id", "kind": "contact", "optional": True},
        {"key": "asset_id", "label": "Asset id", "kind": "asset", "optional": True},
    ],
    "linked_assets": [
        {
            "key": "contact_id",
            "label": "Contact id (shows the assets linked to them)",
            "kind": "contact",
        }
    ],
    "collection": [
        {
            "key": "template_id",
            "label": "Asset template id to show records from",
            "kind": "assetTemplate",
        },
        {
            "key": "link_contact_id",
            "label": "Only show records linked to this contact id",
            "kind": "contact",
            "optional": True,
        },
        {
            "key": "display_fields",
            "label": "Which of the template's own field keys to show",
            "kind": "templateFields",
            "dependsOn": "template_id",
        },
        {
            "key": "status_field",
            "label": "One of the template's own select-type field keys — adds a one-click status control",
            "kind": "templateSelectField",
            "dependsOn": "template_id",
            "optional": True,
        },
        {
            "key": "view",
            "label": "Layout",
            "kind": "select",
            "options": [
                {"value": "list", "label": "List"},
                {"value": "kanban", "label": "Kanban (grouped by status)"},
                {"value": "count", "label": "Count only"},
            ],
        },
    ],
    "documents": [{"key": "asset_id", "label": "Asset id", "kind": "asset"}],
    "linked_tasks": [{"key": "asset_id", "label": "Asset id", "kind": "asset"}],
    "linked_contact": [
        {"key": "asset_id", "label": "Asset id (shows its linked contact)", "kind": "asset"}
    ],
    "note_embed": [{"key": "path", "label": "Note path", "kind": "note"}],
    "journal_entry": [{"key": "date", "label": "Date (YYYY-MM-DD)", "kind": "date"}],
    "single_event": [{"key": "event_id", "label": "Calendar event id", "kind": "event"}],
    "workflow_status": [{"key": "workflow_id", "label": "n8n workflow id", "kind": "workflow"}],
    "text_block": [{"key": "text", "label": "Text", "kind": "textarea"}],
    "link_button": [
        {"key": "label", "label": "Button label", "kind": "text"},
        {"key": "url", "label": "URL (https://...)", "kind": "text"},
    ],
    "heading_divider": [
        {"key": "text", "label": "Heading text (leave blank for a plain divider)", "kind": "text"},
        {
            "key": "style",
            "label": "Style",
            "kind": "select",
            "options": [
                {"value": "heading", "label": "Heading"},
                {"value": "divider", "label": "Divider"},
            ],
        },
    ],
    # Flattened from the frontend's single composite `moduleAndRecord` picker
    # kind (see module docstring) into the three real config keys it sets.
    "nav_button": [
        {
            "key": "module",
            "label": "Module id this button goes to, e.g. 'tasks', 'finance', 'dashboard' "
            "(call get_dashboard_block_catalog or get_help for the full module list)",
            "kind": "text",
        },
        {
            "key": "record_id",
            "label": "Specific record id to jump straight to (omit for the module's whole page)",
            "kind": "text",
            "optional": True,
        },
        {
            "key": "section",
            "label": "Specific section/sub-page within the module, e.g. a Finance tab or a Settings "
            "page (omit when targeting a whole page or a specific record instead)",
            "kind": "text",
            "optional": True,
        },
        {"key": "label", "label": "Button label (optional)", "kind": "text", "optional": True},
    ],
    "status_button": [
        {
            "key": "record_type",
            "label": "What kind of record?",
            "kind": "select",
            "options": [
                {"value": "task", "label": "Task"},
                {"value": "contact", "label": "Contact"},
                {"value": "asset", "label": "Asset"},
            ],
        },
        {
            "key": "task_id",
            "label": "Task id",
            "kind": "task",
            "showIf": {"key": "record_type", "equals": "task"},
        },
        {
            "key": "new_status",
            "label": "Set status to",
            "kind": "select",
            "options": [
                {"value": "pending", "label": "Pending"},
                {"value": "done", "label": "Done"},
                {"value": "skipped", "label": "Skipped"},
            ],
            "showIf": {"key": "record_type", "equals": "task"},
        },
        {
            "key": "contact_id",
            "label": "Contact id",
            "kind": "contact",
            "showIf": {"key": "record_type", "equals": "contact"},
        },
        {
            "key": "contact_field",
            "label": "Which contact field to update (gender or marital_status)",
            "kind": "contactField",
            "showIf": {"key": "record_type", "equals": "contact"},
        },
        {
            "key": "asset_id",
            "label": "Asset id",
            "kind": "asset",
            "showIf": {"key": "record_type", "equals": "asset"},
        },
        {
            "key": "asset_action",
            "label": "Action",
            "kind": "select",
            "options": [
                {"value": "archive", "label": "Archive"},
                {"value": "unarchive", "label": "Unarchive"},
                {"value": "set_field", "label": "Set a field value"},
            ],
            "showIf": {"key": "record_type", "equals": "asset"},
        },
        {
            "key": "select_field",
            "label": "Which of the asset's own select-type template fields to set",
            "kind": "assetSelectField",
            "dependsOn": "asset_id",
            "showIf": {"key": "asset_action", "equals": "set_field"},
        },
        {"key": "label", "label": "Button label (optional)", "kind": "text", "optional": True},
    ],
}


def is_configurable(block_type: str) -> bool:
    return len(AGENT_CONFIG_SCHEMAS.get(block_type, [])) > 0
