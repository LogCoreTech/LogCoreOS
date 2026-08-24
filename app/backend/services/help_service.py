"""help_service.py — single source of truth for in-app help content.

The authored content lives in `content/help.json` and is shipped with the app (versioned
with the release, not user-editable). Three consumers read it through this service:
the Help page (via the /help router), the AI agent (`get_help` tool + capability index),
and the What's-New broadcast.
"""

import json
import logging
from pathlib import Path
from typing import Any

from services.file_service import read_json, user_path, write_json

logger = logging.getLogger("logcore.help")

_CONTENT_PATH = Path(__file__).parent.parent / "content" / "help.json"
_cache: dict[str, Any] | None = None

_EMPTY: dict[str, Any] = {"sections": [], "faq": [], "support": {}, "whats_new": []}


def _static_content() -> dict[str, Any]:
    """The bundled content/help.json file only — cached, since that file is
    static per release."""
    global _cache
    if _cache is None:
        try:
            with open(_CONTENT_PATH) as f:
                _cache = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.exception("help content failed to load from %s", _CONTENT_PATH)
            _cache = _EMPTY
    return _cache


def get_content() -> dict[str, Any]:
    """Static help.json sections merged with every DISCOVERED module's own
    help_section (module_packages/<id>/manifest.py) — NOT cached the way the
    static file is, since which modules are discovered/installed can change
    without a new release. A module's section shows regardless of its
    install state (same "describe everything, not just what's enabled"
    principle as capabilities_index() below) — accepted as a small, static
    amount of always-visible copy per module rather than building help-content
    module-awareness into the Help page's own gating."""
    from module_registry import discover_manifests

    content = dict(_static_content())
    manifests, _errors = discover_manifests()
    module_sections = [m.help_section for m in manifests.values() if m.help_section]
    if module_sections:
        content = {**content, "sections": [*content.get("sections", []), *module_sections]}
    return content


def _section_by_id(section_id: str) -> dict | None:
    for s in get_content().get("sections", []):
        if s.get("id") == section_id:
            return s
    return None


def as_text(section_id: str | None = None) -> str:
    """Render the help content to Markdown for the AI to read and cite.

    Each section ends with its deep-link anchor (`/help#<id>`) so the agent can point
    the user to the exact spot in the Help page. Pass a section_id to narrow the output.
    """
    content = get_content()
    sections = content.get("sections", [])
    if section_id:
        one = _section_by_id(section_id)
        sections = [one] if one else []

    lines: list[str] = []
    for s in sections:
        if not s:
            continue
        lines.append(f"## {s.get('title', s.get('id', ''))}")
        if s.get("blurb"):
            lines.append(s["blurb"])
        if s.get("howto"):
            lines.append("How to use it:")
            for i, step in enumerate(s["howto"], 1):
                lines.append(f"{i}. {step}")
        if s.get("tips"):
            lines.append("Tips:")
            for tip in s["tips"]:
                lines.append(f"- {tip}")
        lines.append(f"(Help section: /help#{s.get('id')})")
        lines.append("")

    # Include the FAQ only on the full render (not when a single section was requested).
    if not section_id and content.get("faq"):
        lines.append("## Frequently Asked Questions")
        for item in content["faq"]:
            lines.append(f"Q: {item.get('q', '')}")
            lines.append(f"A: {item.get('a', '')}")
            lines.append("")

    if not section_id and content.get("support"):
        sup = content["support"]
        lines.append("## Contact & Support")
        lines.append(f"{sup.get('note', '')} Email: {sup.get('email', '')}")

    return "\n".join(lines).strip()


def capabilities_index(enabled_modules: set[str] | list[str] | None = None) -> str:
    """A compact 'module → what it does' index for the AI system context.

    Describes EVERY module, not just enabled ones — a disabled or
    not-installed module still gets a line, annotated with its real state,
    so the AI can proactively say "Journal isn't installed, ask an admin" or
    similar. This is a deliberately SOFT, informational-only channel: it only
    changes what the model is told, never what it can actually call — the
    real tool list (_get_tools() in agent_service.py) stays hard-gated by
    disabled_modules regardless of what this index says. Sections with no
    `modules` (cross-cutting topics like Sharing or Personal vs Business) are
    always included, unannotated.
    """
    from module_registry import discover_manifests
    from services import mod_store_service

    enabled = set(enabled_modules) if enabled_modules is not None else None
    manifests, _errors = discover_manifests()
    not_installed = set(manifests) - mod_store_service.get_installed_ids()

    lines: list[str] = []
    for s in get_content().get("sections", []):
        if s.get("admin_only"):
            continue
        mods = s.get("modules") or []
        blurb = (s.get("blurb") or "").split(". ")[0].rstrip(".")
        title, anchor = s.get("title"), s.get("id")

        if not mods:
            lines.append(f"- {title} (/help#{anchor}): {blurb}.")
            continue

        if enabled is not None and not (set(mods) & enabled):
            if set(mods) & not_installed:
                lines.append(
                    f"- {title}: {blurb}. NOT INSTALLED — available in the Mod Store; "
                    "an admin can install it if the user wants this."
                )
            else:
                lines.append(f"- {title}: {blurb}. Currently turned off for this user.")
            continue

        lines.append(f"- {title} (/help#{anchor}): {blurb}.")

    if not lines:
        return ""
    return (
        "LogCore modules (point the user to the right one when relevant; cite the "
        "/help#<id> anchor for ones they can actually use — the ones marked NOT "
        "INSTALLED or turned off can be mentioned, but their tools aren't available "
        "to you right now):\n" + "\n".join(lines)
    )


def latest_whats_new() -> dict | None:
    """Return the newest What's-New entry (by list order — newest first), or None."""
    entries = get_content().get("whats_new", [])
    return entries[0] if entries else None


# ---------------------------------------------------------------------------
# First-run onboarding checklist state (per user)
# ---------------------------------------------------------------------------


def _onboarding_path(user_name: str) -> Path:
    return user_path(user_name) / "onboarding.json"


def get_onboarding(user_name: str) -> dict:
    return read_json(_onboarding_path(user_name), default={"dismissed": False, "done": []})


def set_onboarding(
    user_name: str,
    dismissed: bool | None = None,
    done: list[str] | None = None,
) -> dict:
    """Merge-update the checklist state: mark steps done (union) and/or dismiss the card."""
    path = _onboarding_path(user_name)
    state = read_json(path, default={"dismissed": False, "done": []})
    if dismissed is not None:
        state["dismissed"] = dismissed
    if done is not None:
        merged = {s[:40] for s in (state.get("done", []) + list(done)) if s}
        state["done"] = sorted(merged)[:30]
    write_json(path, state)
    return state
