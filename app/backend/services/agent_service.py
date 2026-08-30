"""Agent loop — wraps tool-enabled AI completions over user data."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from services import auth_service, notes_service, profile_service, push_service, task_service
from services.ai_provider import agent_completion
from services.file_service import (
    brain_path,
    read_json,
    read_markdown,
    resolve_user_md_path,
    user_path,
    write_json,
    write_markdown,
    ws_path,
)

logger = logging.getLogger("logcore.agent")

MAX_STEPS = 10
_RUNS_CAP = 50
_PENDING_CAP = 20


def _brain_skip(user: dict) -> set[str]:
    """Same reasoning as routers/brain.py's own skip-list — a module's owned
    Brain paths are off-limits to the AI's generic list/read/search tools
    only while that module is disabled for THIS user (conditional, per-user,
    matching every module's own dual-access pattern — not just "never
    installed instance-wide"), unioned with the always-skipped Tasks/
    Dashboards/Assets/Contacts/Finance/Goals folders (structurally different
    shape, JSON+binary files, not markdown)."""
    from module_registry import brain_paths_for_disabled

    disabled = set(user.get("disabled_modules", []))
    return {
        "Tasks",
        "Dashboards",
        "Assets",
        "Contacts",
        "Finance",
        "Goals",
    } | brain_paths_for_disabled(disabled)


# Tools available in research mode — read-only access only
_RESEARCH_TOOLS = {
    "list_brain_files",
    "read_brain_file",
    "get_profile",
    "search_brain",
    "search_web",
    "get_priorities",
    "get_help",
    # admin read-only
    "list_users",
    "read_system_file",
}

# Tools that never modify data — safe to run without per-write approval in
# approve mode. Anything NOT listed here requires approval, so new tools are
# write-gated by default. ask_user_question has no side effects either — it
# pauses via its own dedicated mechanism (see run_agent), never the write-gate.
_READ_TOOLS = _RESEARCH_TOOLS | {"get_home_assistant_state", "ask_user_question"}

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic input_schema format — translated for OpenAI by ai_provider)
# ---------------------------------------------------------------------------

_USER_TOOLS: list[dict] = [
    {
        "name": "list_brain_files",
        "description": "List all markdown files in the user's brain (notes, profile, memory, etc.).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_brain_file",
        "description": "Read the full contents of a brain markdown file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the .md file, e.g. 'Notes/MyNote.md'",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_brain_file",
        "description": "Overwrite an existing brain markdown file. File must already exist — use create_brain_file to make new ones.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to an existing .md file"},
                "content": {"type": "string", "description": "New full content of the file"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "create_brain_file",
        "description": "Create a new markdown file in the user's brain. Fails if the file already exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path for the new .md file, e.g. 'Notes/MyNote.md'",
                },
                "content": {"type": "string", "description": "Initial content (defaults to empty)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_profile",
        "description": (
            "Read the user's full profile — their own Contact record (self_of the user). Fields include: "
            "occupation, gender, city, state, country, pronouns, wake_weekday, wake_weekend, bedtime, "
            "work_start, work_end, height_cm, height_unit, weight_kg, weight_unit, blood_type, diet, "
            "exercise, conditions, medications, marital_status, affiliated_contact_ids (linked family/"
            "company contacts), pets, income_range, budget_style, life_mission, "
            "core_values (list of short strings, not a single comma-separated string), "
            "key_constraints, communication_style, tone, response_language, topics_to_emphasize, "
            "topics_to_avoid, notes, priority_order ({personal: [...], business: [...]}), "
            "career_history (resume-style list: [{title, company_id, industry, education, "
            "years_experience, skills, start_date, end_date, archived}])."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_priorities",
        "description": (
            "Get the ordered life-priority categories (highest first) that weigh tasks and goals. "
            "Consult this BEFORE creating any task or goal so its category aligns with what matters "
            "most. scope 'user' (default) = the user's priorities for the active workspace; "
            "'household' or 'team' = the shared-pool priorities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["user", "household", "team"]},
            },
            "required": [],
        },
    },
    {
        "name": "get_help",
        "description": (
            "Read LogCore's in-app help guide to explain how a feature or module works. Call this "
            "whenever the user asks how to do something, seems confused, or asks what LogCore can do. "
            "Answer from what it returns and point them to the cited /help#<section> anchor. Pass a "
            "section id (e.g. 'finance', 'tasks', 'sharing', 'chat') to focus on one topic, or omit "
            "it to get the whole guide including the FAQ."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Optional help section id to focus on (e.g. finance, tasks, sharing).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "update_profile",
        "description": (
            "Update one or more profile fields on the user's own Contact record. Pass only the fields you "
            "want to change — existing fields are preserved. "
            "Concrete goals belong in the Goals module (create_goal) and day-to-day to-dos in "
            "Tasks (add_task), not here. "
            "This is for biographical/aspirational context: life mission, values, health, family, work, AI preferences."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": 'Dict of profile fields to update, e.g. {"life_mission": "Run a marathon", "occupation": "Engineer"}',
                },
            },
            "required": ["fields"],
        },
    },
    {
        "name": "append_memory",
        "description": "Append a dated note to the user's Short-Term or Long-Term Memory file. Use short for recent context; long for stable facts worth keeping indefinitely.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Markdown text to append"},
                "target": {
                    "type": "string",
                    "enum": ["short", "long"],
                    "description": "Which memory file to append to (default: short)",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "rewrite_memory",
        "description": "Overwrite a memory file entirely with new condensed content. Use this to clean up or compress memory — not for adding new entries (use append_memory for that).",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Full new markdown content for the memory file",
                },
                "target": {
                    "type": "string",
                    "enum": ["short", "long"],
                    "description": "Which memory file to rewrite (default: short)",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "search_brain",
        "description": (
            "Search across the user's Brain markdown files (notes, journal, memory, profile) for a "
            "keyword or phrase. Notes shared with the user or in the household/team pool are searched "
            "too, alongside the user's own; journal/memory/profile search stays scoped to the user's "
            "own files, since those aren't shareable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Case-insensitive search term"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "send_notification",
        "description": "Send a push notification to the user via their configured ntfy channel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Notification title"},
                "body": {"type": "string", "description": "Notification body text"},
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "update_timezone",
        "description": "Update the user's timezone. Use an IANA timezone string, e.g. 'America/New_York', 'Europe/London', 'Asia/Tokyo'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "description": "IANA timezone string"},
            },
            "required": ["timezone"],
        },
    },
    {
        "name": "propose_plan",
        "description": (
            "Present a plan to the user for approval BEFORE taking any write actions "
            "(creating, updating, or deleting tasks, notes, files, or memory). "
            "Call this first. Do not call other write tools in the same turn — wait for the user to confirm."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Plain-English summary of what you're about to do",
                },
                "actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific steps you plan to take, e.g. ['Create task: Call dentist (Health, High priority)', 'Set due date to 2024-01-15']",
                },
            },
            "required": ["summary", "actions"],
        },
    },
    {
        "name": "ask_user_question",
        "description": (
            "Ask the user a clarifying multiple-choice question when their request is ambiguous or "
            "a real decision needs their input before you proceed — mirrors the ask-a-question tool "
            "available in coding-agent sessions. Use this instead of guessing or silently picking a "
            "default. Execution pauses in EVERY mode (including auto) until they answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask, ending in a question mark.",
                },
                "header": {
                    "type": "string",
                    "description": "A very short label for the question (max ~12 chars), e.g. 'Category' or 'Approach'.",
                },
                "options": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Short display text for this choice.",
                            },
                            "description": {
                                "type": "string",
                                "description": "What this option means or implies.",
                            },
                        },
                        "required": ["label", "description"],
                    },
                    "description": "2-4 choices, mutually exclusive unless multi_select is true.",
                },
                "multi_select": {
                    "type": "boolean",
                    "description": "True if the user may pick more than one option.",
                },
            },
            "required": ["question", "header", "options", "multi_select"],
        },
    },
    {
        "name": "run_suggestion",
        "description": "Immediately trigger a proactive suggestion by ID. Built-in IDs: 'daily_digest', 'overdue_alert', 'weekly_review', 'goal_drift', 'goal_due_urgency'. Custom suggestions use their UUID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "suggestion_id": {
                    "type": "string",
                    "description": "Built-in name or custom UUID of the suggestion to run",
                },
            },
            "required": ["suggestion_id"],
        },
    },
    {
        "name": "update_suggestion",
        "description": "Enable/disable a suggestion or change its delivery settings. Built-in IDs: 'daily_digest', 'overdue_alert', 'weekly_review', 'goal_drift', 'goal_due_urgency'. Custom suggestions use their UUID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "suggestion_id": {"type": "string", "description": "Built-in name or custom UUID"},
                "enabled": {"type": "boolean", "description": "Enable or disable this suggestion"},
                "delivery": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["push", "in_app", "chat"]},
                    "description": "Delivery channels",
                },
                "hour": {
                    "type": "integer",
                    "description": "Hour to fire (0-23, null = system default for built-ins)",
                },
                "days_threshold": {
                    "type": "integer",
                    "description": "Days without progress before goal_drift fires (goal_drift only)",
                },
            },
            "required": ["suggestion_id"],
        },
    },
    {
        "name": "create_suggestion",
        "description": (
            "Create a new recurring AI-powered suggestion. The AI will run your prompt on schedule and deliver the result. "
            "Schedule modes: 'daily' (every day at hour), 'interval' (every N days at hour, requires interval_days), "
            "'weekly' (specific weekday at hour, requires day_of_week like 'mon'–'sun')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short display name, e.g. 'Evening wind-down'",
                },
                "prompt": {
                    "type": "string",
                    "description": "Prompt sent to the AI when this suggestion fires",
                },
                "hour": {"type": "integer", "description": "Hour to fire (0-23)"},
                "delivery": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["push", "in_app", "chat"]},
                    "description": "Delivery channels (default: ['in_app'])",
                },
                "schedule": {
                    "type": "string",
                    "enum": ["daily", "interval", "weekly"],
                    "description": "Schedule type (default: 'daily')",
                },
                "interval_days": {
                    "type": "integer",
                    "description": "Required when schedule='interval': fire every N days",
                },
                "day_of_week": {
                    "type": "string",
                    "description": "Required when schedule='weekly': 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', or 'sun'",
                },
            },
            "required": ["name", "prompt", "hour"],
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the internet for current information, news, or any topic not in the user's Brain. "
            "Returns titles, URLs, and content snippets. Available in research mode."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Max results (default 5, max 10)",
                },
            },
            "required": ["query"],
        },
    },
]

_ADMIN_TOOLS: list[dict] = [
    {
        "name": "list_users",
        "description": "List all users in the system with basic info (admin only).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_system_file",
        "description": "Read a system-level Brain file that applies to all users (admin only). Use update_profile for personal AI preferences instead.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "enum": ["SOUL.md", "AGENTS.md", "USERS.md", "MEMORY_MAP.md"],
                    "description": "System Brain file to read",
                },
            },
            "required": ["filename"],
        },
    },
    {
        "name": "update_system_file",
        "description": "Overwrite a system-level Brain file (admin only). Changes affect all users. Use with care.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "enum": ["SOUL.md", "AGENTS.md", "USERS.md", "MEMORY_MAP.md"],
                    "description": "System Brain file to update",
                },
                "content": {"type": "string", "description": "Full new markdown content"},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "run_tests",
        "description": "Run the backend test suite (pytest) and return the output. Admin only. Use to check that the codebase is healthy after making changes.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def _module_tool_dispatch() -> dict[str, tuple[str, Callable]]:
    """{tool_name: (module_id, execute_fn)} built fresh from every ACTIVE
    module's agent_tools.py. O(1) dispatch for the executor's fallback case,
    rather than iterating modules and calling each in turn. Computed fresh
    (not cached at import time) so it reflects live install state, same
    reasoning as everything else install-state-dependent in this system."""
    from module_registry import active_manifests

    dispatch: dict[str, tuple[str, Callable]] = {}
    for module_id, manifest in active_manifests().items():
        if not manifest.owned_agent_tools:
            continue
        try:
            import importlib

            mod = importlib.import_module(f"module_packages.{module_id}.backend.agent_tools")
        except Exception:
            logger.exception(
                "module_packages/%s: agent_tools failed to import — its tools unavailable",
                module_id,
            )
            continue
        for tool_name in manifest.owned_agent_tools:
            dispatch[tool_name] = (module_id, mod.execute)
    return dispatch


def _module_tool_schemas() -> list[dict]:
    """Tool schemas contributed by every ACTIVE module's agent_tools.py."""
    from module_registry import active_manifests

    schemas: list[dict] = []
    for module_id, manifest in active_manifests().items():
        if not manifest.owned_agent_tools:
            continue
        try:
            import importlib

            mod = importlib.import_module(f"module_packages.{module_id}.backend.agent_tools")
            schemas.extend(mod.TOOL_SCHEMAS)
        except Exception:
            logger.exception("module_packages/%s: agent_tools schemas failed to load", module_id)
    return schemas


def _get_tools(user: dict) -> list[dict]:
    from services.ha_service import is_configured as _ha_configured

    _HA_TOOL_NAMES = {
        "get_home_assistant_state",
        "control_home_assistant_device",
        "activate_scene",
        "trigger_home_assistant_automation",
    }
    ha_ok = _ha_configured()
    disabled = set(user.get("disabled_modules", []))
    tools = list(_USER_TOOLS)

    # Module-contributed tools: hard-gated by disabled_modules, same as every
    # other enforcement-gap fix in this system — a disabled/uninstalled
    # module's tools are never even offered to the model, so it can never
    # attempt a call that's guaranteed to fail (see help_service's
    # capabilities_index() for the SEPARATE, softer "the AI knows this
    # module exists but isn't installed" awareness channel).
    from module_registry import discover_manifests

    manifests, _errors = discover_manifests()
    owned_by_disabled: set[str] = set()
    for module_id, manifest in manifests.items():
        if module_id in disabled:
            owned_by_disabled.update(manifest.owned_agent_tools)

    # A module's admin_agent_tools (e.g. household's shared-task management
    # tools) are only OFFERED to admin callers, mirroring core _ADMIN_TOOLS'
    # own gate below — the executor itself may still enforce a finer-grained
    # check on top (complete_shared_task's admin-or-assignee check is a real
    # example), but a non-admin should never even see these in its tool list.
    from module_registry import admin_agent_tool_names

    is_admin = user.get("role") == "admin"
    admin_only = admin_agent_tool_names()
    tools.extend(
        t
        for t in _module_tool_schemas()
        if t["name"] not in owned_by_disabled and (is_admin or t["name"] not in admin_only)
    )

    # The 4 HA tools (module-contributed via home_assistant/ since 2026-08-24)
    # need HA to actually be *configured*, not just installed+enabled —
    # installed only means the module's code is wired in; configured means
    # an admin has set a URL+token in Admin → Hosting. Applied as a final
    # pass over the combined list so it's agnostic to which source a tool's
    # schema came from.
    tools = [t for t in tools if ha_ok or t["name"] not in _HA_TOOL_NAMES]

    if is_admin:
        tools.extend(_ADMIN_TOOLS)
    return tools


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


def _execute_tool(
    name: str,
    inputs: dict,
    user: dict,
    workspace: str = "personal",
    cross_workspace: bool = False,
) -> Any:
    """Run one tool; return result or an error dict — never raises."""
    try:
        match name:
            case "list_brain_files":
                base = ws_path(user["name"], workspace)
                if not base.exists():
                    return []
                files = []
                skip = _brain_skip(user)
                for p in sorted(base.rglob("*.md")):
                    rel = p.relative_to(base)
                    if not any(part in skip for part in rel.parts):
                        files.append({"path": str(rel), "name": p.name})
                return files

            case "read_brain_file":
                raw = inputs["path"].lstrip("/")
                parts = raw.split("/")
                if any(p in ("", ".", "..") for p in parts) or not raw.endswith(".md"):
                    return {"error": "Access denied"}
                base = ws_path(user["name"], workspace)
                candidate = (base / raw).resolve()
                if not candidate.is_relative_to(user_path(user["name"]).resolve()):
                    return {"error": "Access denied"}
                if not candidate.exists():
                    return {"error": f"File not found: {inputs['path']!r}"}
                return read_markdown(candidate)

            case "write_brain_file":
                path = resolve_user_md_path(user["name"], inputs["path"])
                if not path.exists():
                    return {
                        "error": f"File not found: {inputs['path']!r}. Use create_brain_file for new files."
                    }
                write_markdown(path, inputs["content"])
                return {"ok": True}

            case "create_brain_file":
                path = resolve_user_md_path(user["name"], inputs["path"])
                if path.exists():
                    return {
                        "error": f"File already exists: {inputs['path']!r}. Use write_brain_file to edit it."
                    }
                write_markdown(path, inputs.get("content", ""))
                return {"ok": True, "created": inputs["path"]}

            case "get_profile":
                from services import contacts_service

                return contacts_service.get_self_contact(user["name"], create_if_missing=True)

            case "get_help":
                from services import help_service

                return {"help": help_service.as_text(inputs.get("section") or None)}

            case "get_priorities":
                scope = inputs.get("scope", "user")
                if scope in ("household", "team"):
                    pool = "_household" if scope == "household" else "_team"
                    return {"scope": scope, "order": profile_service.get_priority_order(pool)}
                return {
                    "scope": workspace,
                    "order": profile_service.get_priority_order(user["name"], workspace),
                }

            case "update_profile":
                from services import contacts_service

                self_contact = contacts_service.get_self_contact(
                    user["name"], create_if_missing=True
                )
                try:
                    return contacts_service.update_contact(
                        contacts_service.POOL_HOUSEHOLD,
                        "personal",
                        self_contact["id"],
                        inputs.get("fields", {}),
                    )
                except ValueError as exc:
                    return {"error": str(exc)}

            case "append_memory":
                from datetime import date

                target = inputs.get("target", "short")
                fname = "Long_Term_Memory.md" if target == "long" else "Short_Term_Memory.md"
                mem_path = ws_path(user["name"], workspace) / fname
                today = date.today().isoformat()
                existing = mem_path.read_text() if mem_path.exists() else ""
                safe_content = inputs["content"].replace("</brain_data>", "[/brain_data]")
                updated = existing.rstrip() + f"\n\n## {today}\n\n{safe_content}\n"
                write_markdown(mem_path, updated)
                return {"ok": True, "target": fname}

            case "rewrite_memory":
                target = inputs.get("target", "short")
                fname = "Long_Term_Memory.md" if target == "long" else "Short_Term_Memory.md"
                mem_path = ws_path(user["name"], workspace) / fname
                safe_content = inputs["content"].replace("</brain_data>", "[/brain_data]")
                write_markdown(mem_path, safe_content)
                return {"ok": True, "target": fname}

            case "search_brain":
                query = inputs["query"].lower()
                personal_base = user_path(user["name"])
                business_base = personal_base / "Business"
                if cross_workspace:
                    search_roots = [
                        ("personal", personal_base),
                        ("business", business_base),
                    ]
                else:
                    search_roots = [(workspace, ws_path(user["name"], workspace))]

                def _snippet(text: str) -> str | None:
                    idx = text.lower().find(query)
                    if idx == -1:
                        return None
                    start = max(0, idx - 100)
                    end = min(len(text), idx + 200)
                    return text[start:end].strip()

                results = []
                skip = _brain_skip(user)
                for ws_label, base in search_roots:
                    if not base.exists():
                        continue
                    for p in sorted(base.rglob("*.md")):
                        rel = p.relative_to(base)
                        if any(part in skip for part in rel.parts):
                            continue
                        try:
                            text = p.read_text()
                        except OSError:
                            continue
                        snippet = _snippet(text)
                        if snippet is None:
                            continue
                        path_label = f"{ws_label}/{rel}" if cross_workspace else str(rel)
                        results.append({"path": path_label, "snippet": snippet, "owner": None})

                # Shared/pool notes — own files above are covered by the rglob
                # walk (and already gated by `skip`, since Notes is in it when
                # the module's disabled for this user); journal/memory/profile
                # stay own-files-only since none of those are shareable. This
                # loop reaches OTHER stores' notes directly via notes_service,
                # bypassing the rglob walk's own gate entirely — skip it here
                # too, using the same `skip` set, or a disabled user could
                # still search shared-to-them/pool note content even though
                # their own Notes/ folder is correctly hidden above.
                for ws_label, _base in ([] if "Notes" in skip else search_roots):
                    visible = notes_service.list_visible_notes(
                        user["name"],
                        user.get("feature_role", "member"),
                        user.get("role") == "admin",
                        ws_label,
                        include_archived=True,
                    )
                    for item in visible:
                        owner = item.get("_owner")
                        if not owner or item.get("type") != "note":
                            continue
                        store_user = notes_service.store_for_owner(owner, user["name"])
                        note = notes_service.get_note(store_user, item["path"], ws_label)
                        if not note:
                            continue
                        snippet = _snippet(note.get("content") or "")
                        if snippet is None:
                            continue
                        # Matches the own-files path label above exactly (full
                        # brain-relative, with the Notes/ prefix and .md
                        # extension) — read_note/update_note still want the
                        # bare Notes-relative form, same pre-existing gap a
                        # model already has to bridge for its own search hits.
                        note_rel = f"Notes/{item['path']}.md"
                        path_label = f"{ws_label}/{note_rel}" if cross_workspace else note_rel
                        results.append({"path": path_label, "snippet": snippet, "owner": owner})
                return results

            case "send_notification":
                sent = push_service.send_push(user["name"], inputs["title"], inputs["body"])
                return {"sent": sent}

            case "update_timezone":
                from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

                try:
                    ZoneInfo(inputs["timezone"])
                except (ZoneInfoNotFoundError, KeyError):
                    return {"error": f"Invalid timezone: {inputs['timezone']!r}"}
                u = auth_service.get_user_by_name(user["name"])
                if not u:
                    return {"error": "User not found"}
                auth_service.update_user(u["id"], {"timezone": inputs["timezone"]})
                return {"ok": True, "timezone": inputs["timezone"]}

            case "propose_plan":
                # Only ever reached via the resume path once approved — run_agent
                # itself intercepts the call to pause for confirmation before this
                # executes (2026-08-09; was a bare echo relying entirely on the
                # system prompt telling the model to wait, the same shape of gap
                # the approve-mode replay bug had).
                return {"status": "approved"}

            case "list_users":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                from services.auth_service import _load_auth

                safe = {"id", "name", "email", "role", "timezone"}
                return [{k: v for k, v in u.items() if k in safe} for u in _load_auth()["users"]]

            case "read_system_file":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                _ALLOWED_SYSTEM = {"SOUL.md", "AGENTS.md", "USERS.md", "MEMORY_MAP.md"}
                fname = inputs["filename"]
                if fname not in _ALLOWED_SYSTEM:
                    return {"error": f"Not an allowed system file: {fname!r}"}
                p = brain_path() / fname
                if not p.exists():
                    return {"error": f"{fname} not found"}
                return read_markdown(p)

            case "update_system_file":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                _ALLOWED_SYSTEM = {"SOUL.md", "AGENTS.md", "USERS.md", "MEMORY_MAP.md"}
                fname = inputs["filename"]
                if fname not in _ALLOWED_SYSTEM:
                    return {"error": f"Not an allowed system file: {fname!r}"}
                safe_content = inputs["content"].replace("</brain_data>", "[/brain_data]")
                write_markdown(brain_path() / fname, safe_content)
                return {"ok": True, "updated": fname}

            case "run_suggestion":
                # This tool executor is called synchronously inside the agent loop.
                # For custom suggestions (which need async AI calls), we use a thread pool to run asyncio.
                import concurrent.futures

                from services import suggestions_service as sug_svc

                sid = inputs["suggestion_id"]
                cfg = sug_svc.get_config(user["name"])
                is_custom = any(c["id"] == sid for c in cfg.get("custom", []))
                if is_custom:
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        fut = pool.submit(sug_svc.run_suggestion_sync, user["name"], sid)
                        return fut.result(timeout=60)
                return sug_svc.run_suggestion_sync(user["name"], sid)

            case "update_suggestion":
                from services import suggestions_service as sug_svc

                sid = inputs["suggestion_id"]
                updates = {k: v for k, v in inputs.items() if k != "suggestion_id"}
                if not updates:
                    return {"error": "No fields to update"}
                return sug_svc.update_config(user["name"], sid, updates)

            case "create_suggestion":
                import scheduler as sched_mod  # noqa: PLC0415
                from services import suggestions_service as sug_svc

                new_s = sug_svc.create_custom(user["name"], inputs)
                if new_s.get("enabled", True):
                    try:
                        sched_mod.add_custom_job(user["name"], new_s)
                    except Exception:
                        pass
                return new_s

            case "run_tests":
                if user.get("role") != "admin":
                    return {"error": "Admin access required"}
                import subprocess
                from pathlib import Path as _Path

                backend_dir = _Path(__file__).parent.parent
                result = subprocess.run(
                    ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"],
                    capture_output=True,
                    text=True,
                    cwd=backend_dir,
                    timeout=120,
                )
                output = result.stdout + (result.stderr if result.returncode != 0 else "")
                return {
                    "passed": result.returncode == 0,
                    "output": output.strip(),
                }

            case "search_web":
                from services.web_search_service import search as _web_search

                q = inputs["query"]
                n = int(inputs.get("max_results", 5))
                return _web_search(q, n)

            case _:
                dispatch = _module_tool_dispatch()
                entry = dispatch.get(name)
                if entry is not None:
                    _module_id, execute_fn = entry
                    result = execute_fn(name, inputs, user, workspace)
                    if result is not None:
                        return result
                return {"error": f"Unknown tool: {name!r}"}

    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Tool error: {exc}"}


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


async def run_agent(
    user: dict,
    goal: str,
    history: list[dict],
    system: str,
    mode: str = "plan",
    workspace: str = "personal",
    cross_workspace: bool = False,
    resume: dict | None = None,
    max_steps: int | None = None,
    chat_id: str | None = None,
) -> dict:
    """Run the agent loop and return a run record.

    `resume` replays a previously-paused turn instead of starting fresh: `messages`
    comes from the persisted pending-turn record (`goal`/`history` are ignored), the
    paused tool call(s) are executed/answered/declined exactly as originally
    proposed — never re-derived from the model's own prior text — and the loop then
    continues normally so the model can react to the result. `resume["kind"]` is
    `"write"` (execute via `_execute_tool`, or synthesize a declined result if
    `resume["decision"] == "decline"`) or `"question"` (use `resume["answer"]` as
    the tool result — the "tool" here is the human, nothing to execute).
    """
    run_id = (resume or {}).get("run_id") or str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    # Drop the pending_write/pending_question/pending_plan entry being resolved
    # right now — it's what's *about* to be replayed/answered below, not still
    # open. Leaving it in would leak a resolved pause into a later, genuinely
    # completed response's steps: the frontend's pendingWrites/pendingQuestion
    # detection doesn't cross-check `mode`, so it would render a phantom
    # approval card with no real run_id behind it (the completed response
    # never carries one) — clicking it sends `resume.run_id: undefined`, which
    # JSON.stringify drops entirely, and the API 422s with "field required".
    steps: list[dict] = [
        s
        for s in (resume or {}).get("steps", [])
        if s.get("type") not in ("pending_write", "pending_question", "pending_plan")
    ]
    tools_used = False
    final_answer = ""
    status = "completed"
    last_text = ""
    step_limit = max_steps if max_steps is not None else MAX_STEPS

    if resume:
        messages = list(resume["messages"])
        replay_results = []
        for tc in resume["pending_tool_calls"]:
            if resume.get("kind") == "question":
                result: Any = {"answer": resume.get("answer")}
            elif resume.get("decision") == "decline":
                result = {"declined": True}
            else:
                result = _execute_tool(
                    tc["name"],
                    tc["input"],
                    user,
                    workspace=workspace,
                    cross_workspace=cross_workspace,
                )
            steps.append(
                {
                    "type": "tool_call",
                    "tool": tc["name"],
                    "input": tc["input"],
                    "output": result,
                    "step": 0,
                }
            )
            result_str = json.dumps(result) if not isinstance(result, str) else result
            replay_results.append(
                {"type": "tool_result", "tool_use_id": tc["id"], "content": result_str}
            )
        messages.append({"role": "user", "content": replay_results})
        tools_used = True
    else:
        messages = list(history) + [{"role": "user", "content": goal}]

    all_tools = _get_tools(user)
    if mode in ("auto", "approve"):
        active_tools = [t for t in all_tools if t["name"] != "propose_plan"]
    elif mode == "research":
        from module_registry import read_only_agent_tool_names

        research_tools = _RESEARCH_TOOLS | read_only_agent_tool_names()
        active_tools = [t for t in all_tools if t["name"] in research_tools]
    else:  # plan
        active_tools = all_tools

    for step_num in range(step_limit):
        response = await agent_completion(
            system, messages, active_tools, user_name=user["name"], workspace=workspace
        )
        last_text = response.text

        if not response.tool_calls or response.stop_reason != "tool_use":
            final_answer = response.text
            if response.stop_reason == "max_tokens":
                status = "max_steps_reached"
            break

        # A clarifying question pauses in EVERY mode, checked before the
        # approve-mode write-gate below — if the model asks a question alongside
        # a write call in the same turn, the question always wins (nothing about
        # answering a question is mode-dependent the way a write is).
        ask_call = next((tc for tc in response.tool_calls if tc.name == "ask_user_question"), None)
        if ask_call:
            if response.text:
                steps.append({"type": "thought", "content": response.text, "step": step_num})
            steps.append(
                {
                    "type": "pending_question",
                    "question": ask_call.input.get("question"),
                    "header": ask_call.input.get("header"),
                    "options": ask_call.input.get("options"),
                    "multi_select": ask_call.input.get("multi_select", False),
                    "step": step_num,
                }
            )
            messages.append({"role": "assistant", "content": response.raw_content})
            save_pending_turn(
                user["name"],
                {
                    "run_id": run_id,
                    "chat_id": chat_id,
                    "kind": "question",
                    "mode": mode,
                    "goal": goal,
                    "messages": messages,
                    "pending_tool_calls": [
                        {"id": ask_call.id, "name": ask_call.name, "input": ask_call.input}
                    ],
                    "steps": steps,
                    "workspace": workspace,
                    "cross_workspace": cross_workspace,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            status = "awaiting_answer"
            final_answer = response.text or "I have a question before continuing."
            break

        # A proposed plan pauses the same way — propose_plan is only ever
        # offered in plan mode (see active_tools above), and used to be a bare
        # echo relying entirely on the system prompt telling the model to
        # wait, the same shape of gap the approve-mode replay bug had.
        plan_call = next((tc for tc in response.tool_calls if tc.name == "propose_plan"), None)
        if plan_call:
            if response.text:
                steps.append({"type": "thought", "content": response.text, "step": step_num})
            steps.append(
                {
                    "type": "pending_plan",
                    "summary": plan_call.input.get("summary"),
                    "actions": plan_call.input.get("actions", []),
                    "step": step_num,
                }
            )
            messages.append({"role": "assistant", "content": response.raw_content})
            save_pending_turn(
                user["name"],
                {
                    "run_id": run_id,
                    "chat_id": chat_id,
                    "kind": "plan",
                    "mode": mode,
                    "goal": goal,
                    "messages": messages,
                    "pending_tool_calls": [
                        {"id": plan_call.id, "name": plan_call.name, "input": plan_call.input}
                    ],
                    "steps": steps,
                    "workspace": workspace,
                    "cross_workspace": cross_workspace,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            status = "awaiting_approval"
            final_answer = (
                response.text or "Here's my plan — let me know if you'd like me to proceed."
            )
            break

        # Approve mode: pause before any write — nothing in this response is
        # executed; the frontend shows the pending writes for user approval.
        if mode == "approve":
            from module_registry import read_only_agent_tool_names

            read_tools = _READ_TOOLS | read_only_agent_tool_names()
            pending = [tc for tc in response.tool_calls if tc.name not in read_tools]
            if pending:
                if response.text:
                    steps.append({"type": "thought", "content": response.text, "step": step_num})
                for tc in pending:
                    steps.append(
                        {
                            "type": "pending_write",
                            "tool": tc.name,
                            "input": tc.input,
                            "step": step_num,
                        }
                    )
                # Persist exactly what was proposed so Approve replays this precise
                # call instead of the model re-guessing from its own prior text
                # (the original bug — see docs/MEMORY.md 2026-08-09 for the writeup).
                messages.append({"role": "assistant", "content": response.raw_content})
                save_pending_turn(
                    user["name"],
                    {
                        "run_id": run_id,
                        "chat_id": chat_id,
                        "kind": "write",
                        "mode": mode,
                        "goal": goal,
                        "messages": messages,
                        "pending_tool_calls": [
                            {"id": tc.id, "name": tc.name, "input": tc.input} for tc in pending
                        ],
                        "steps": steps,
                        "workspace": workspace,
                        "cross_workspace": cross_workspace,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                status = "awaiting_approval"
                final_answer = response.text or "I need your approval to make these changes."
                break

        # Tool-use turn
        tools_used = True
        if response.text:
            steps.append({"type": "thought", "content": response.text, "step": step_num})

        messages.append({"role": "assistant", "content": response.raw_content})

        tool_results = []
        for tc in response.tool_calls:
            step_entry: dict = {
                "type": "tool_call",
                "tool": tc.name,
                "input": tc.input,
                "step": step_num,
            }
            steps.append(step_entry)

            result = _execute_tool(
                tc.name, tc.input, user, workspace=workspace, cross_workspace=cross_workspace
            )
            step_entry["output"] = result

            result_str = json.dumps(result) if not isinstance(result, str) else result
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result_str,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    else:
        status = "max_steps_reached"
        final_answer = last_text or "Reached maximum steps."

    if tools_used and status == "completed":
        status = "agent"

    run = {
        "id": run_id,
        "goal": (resume or {}).get("goal", goal),
        "status": status,
        "steps": steps,
        "final_answer": final_answer,
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "step_count": sum(1 for s in steps if s["type"] == "tool_call"),
    }

    if tools_used:
        _save_run(user["name"], run)

    return run


def _save_run(user_name: str, run: dict) -> None:
    path = user_path(user_name) / "agent" / "runs.json"
    data = read_json(path, default={"runs": []})
    data["runs"].insert(0, run)
    data["runs"] = data["runs"][:_RUNS_CAP]
    write_json(path, data)


def _pending_turns_path(user_name: str):
    return user_path(user_name) / "agent" / "pending_turns.json"


def save_pending_turn(user_name: str, pending: dict) -> None:
    """Persist a paused turn (write approval or, later, a question) so a resume
    request can replay/answer the exact thing that was proposed. Not prefixed
    private since routers/chat.py calls this directly on the pause path."""
    path = _pending_turns_path(user_name)
    data = read_json(path, default={"pending": []})
    # A run can only ever have one live pending turn — replace, don't accumulate.
    data["pending"] = [p for p in data["pending"] if p["run_id"] != pending["run_id"]]
    data["pending"].insert(0, pending)
    data["pending"] = data["pending"][:_PENDING_CAP]
    write_json(path, data)


def load_pending_turn(user_name: str, run_id: str) -> dict | None:
    data = read_json(_pending_turns_path(user_name), default={"pending": []})
    return next((p for p in data["pending"] if p["run_id"] == run_id), None)


def get_pending_turn_by_chat_id(user_name: str, chat_id: str) -> dict | None:
    """The live pending_write/pending_question/pending_plan card for one
    conversation, if it currently has one — reopening a saved chat archive
    (a plain .md, no structured step data) previously lost this entirely:
    the assistant's prompt text ("I need your approval...") reloaded fine,
    but the actual interactive card (and its run_id, needed to act on it)
    did not, so a paused approval/question/plan effectively vanished on
    reload with no way to act on it except starting over (2026-08-15).
    `routers/chat.py`'s GET /chat/pending/{chat_id} re-attaches this record's
    `steps`/`mode`/`run_id` onto the last message when Chat.jsx reopens a
    session whose chat_sessions.json status is awaiting_approval/awaiting_answer."""
    data = read_json(_pending_turns_path(user_name), default={"pending": []})
    return next((p for p in data["pending"] if p.get("chat_id") == chat_id), None)


def delete_pending_turn(user_name: str, run_id: str) -> None:
    """Consume a pending turn so it can't be replayed twice (e.g. a double-submit
    of the Approve click) — called once, right after a successful load."""
    path = _pending_turns_path(user_name)
    data = read_json(path, default={"pending": []})
    data["pending"] = [p for p in data["pending"] if p["run_id"] != run_id]
    write_json(path, data)


# ---------------------------------------------------------------------------
# Chat sessions (2026-08-15) — one entry per conversation (chat_id), letting
# the frontend show a "Chats" list with real status instead of a plain saved-
# archive list, and giving background-completed/paused turns somewhere to
# register as unread. Not the archive itself (still a plain .md in Chats/,
# written by routers/chat.py's _write_chat_archive) — this is the index over
# it: {chat_id, filename, title, status, unread, updated_at, last_message_preview}.
# Workspace-scoped (stored under ws_path, like the Chats/ archives themselves,
# not the workspace-agnostic user_path other agent/*.json files use) — a
# conversation's legs always live in one workspace's own Chats/ folder, so its
# index entry has to live there too, or switching workspace mid-conversation
# would silently point the same chat_id at two different physical files.
_SESSIONS_CAP = 50


def _sessions_path(user_name: str, workspace: str):
    return ws_path(user_name, workspace) / "agent" / "chat_sessions.json"


def load_sessions(user_name: str, workspace: str) -> list[dict]:
    return read_json(_sessions_path(user_name, workspace), default={"sessions": []})["sessions"]


def get_session(user_name: str, workspace: str, chat_id: str) -> dict | None:
    return next((s for s in load_sessions(user_name, workspace) if s["chat_id"] == chat_id), None)


def upsert_session(user_name: str, workspace: str, chat_id: str, **fields) -> dict:
    """Create or update one session entry, moving it to the front (most-
    recently-touched-first, same ordering convention as _save_run's runs.json)."""
    path = _sessions_path(user_name, workspace)
    data = read_json(path, default={"sessions": []})
    sessions = data["sessions"]
    existing = next((s for s in sessions if s["chat_id"] == chat_id), None)
    if existing:
        sessions.remove(existing)
        existing.update(fields)
        entry = existing
    else:
        entry = {"chat_id": chat_id, **fields}
    sessions.insert(0, entry)
    data["sessions"] = sessions[:_SESSIONS_CAP]
    write_json(path, data)
    return entry


def mark_session_read(user_name: str, workspace: str, chat_id: str) -> bool:
    path = _sessions_path(user_name, workspace)
    data = read_json(path, default={"sessions": []})
    entry = next((s for s in data["sessions"] if s["chat_id"] == chat_id), None)
    if not entry:
        return False
    entry["unread"] = False
    write_json(path, data)
    return True


def delete_session_by_filename(user_name: str, workspace: str, filename: str) -> None:
    """Called when a saved chat archive is deleted, so its session entry
    (and the now-dangling filename it points at) doesn't linger."""
    path = _sessions_path(user_name, workspace)
    data = read_json(path, default={"sessions": []})
    data["sessions"] = [s for s in data["sessions"] if s.get("filename") != filename]
    write_json(path, data)


# ---------------------------------------------------------------------------
# Chat presence (2026-08-15) — lets routers/chat.py skip a completion/
# approval notification when the requesting user is still actively looking
# at that exact conversation (owner ask: "ai chat only needs to send a
# notification... when the user is not on that module"). POST /chat is a
# synchronous request with no live channel back to the server once it's
# fired, so the server has no way to know "is the tab still open on this
# chat" on its own — Chat.jsx pings this on mount/switch and on an interval
# while the tab is open and visible, so it goes stale on its own once the
# user backgrounds the tab or navigates away, without needing an explicit
# "I left" signal. Deliberately a single most-recent value per user, not
# per-chat_id history — a user only ever actively looks at one conversation
# in one tab at a time; a second open tab just overwrites it with whichever
# ping lands last, an acceptable approximation for a notification nicety.
# Not workspace-scoped, like pending_turns.json — chat_id alone identifies
# the conversation regardless of workspace.
_PRESENCE_STALE_AFTER_SECONDS = 45


def _presence_path(user_name: str):
    return user_path(user_name) / "agent" / "chat_presence.json"


def record_chat_presence(user_name: str, chat_id: str) -> None:
    write_json(
        _presence_path(user_name),
        {"chat_id": chat_id, "seen_at": datetime.now(timezone.utc).isoformat()},
    )


def is_chat_present(user_name: str, chat_id: str) -> bool:
    """True if the user pinged presence for this exact chat_id recently
    enough to assume they're still looking at it right now."""
    data = read_json(_presence_path(user_name), default={})
    if data.get("chat_id") != chat_id or not data.get("seen_at"):
        return False
    try:
        seen_at = datetime.fromisoformat(data["seen_at"])
    except ValueError:
        return False
    age = (datetime.now(timezone.utc) - seen_at).total_seconds()
    return age <= _PRESENCE_STALE_AFTER_SECONDS
