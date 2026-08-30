"""Chat module manifest — the second LOCKED (uninstallable=True) module
conversion, after Tasks. See module_registry.py for the ModuleManifest
contract and docs/MEMORY.md's 2026-08-25/26 entries for the full design.

services/agent_service.py — the whole AI tool-orchestration engine (run_agent,
the pending-turn mechanism, the chat_sessions.json index, presence tracking,
the module-tool dispatch table every OTHER converted module's own
agent_tools.py feeds into) — deliberately never converts and never appears
in the Mod Store at all, same category as dashboard_blocks/registry.py:
imported by every module (including this one), owned by none. Confirmed by
direct read before this conversion started: agent_service.py has zero
imports from any router, zero chat-HTTP-shape assumptions anywhere in it,
and zero module-gating logic of its own — require_module("chat") is purely
this router's own job. module_registry.py's own register_routers()
docstring already named Chat alongside Tasks/Dashboards as a "deeply
load-bearing module" before this conversion existed, independent
confirmation the locked/core-infrastructure split here was already
anticipated correctly.

owned_brain_paths=["Chats"] closes a real, previously-open enforcement gap
found during this conversion: chat archives (a real user's own
Chats/*.md files) had NO Brain-browser/AI-tool protection at all before
this — routers/brain.py's _ALWAYS_SKIP only ever covered "Tasks"/"Business"
(a structural JSON-vs-markdown distinction, not a module gate), and
Chats/*.md is genuinely just markdown a disabled user's own archives sat
fully readable through both the Brain page and the AI's own
list_brain_files/read_brain_file/search_brain tools. This is the
CONDITIONAL variant (hidden only when chat is disabled for that user, same
as Notes/Contacts) — not the unconditional Tasks/Business exception, since
chat archives are ordinary per-user markdown, not a structurally different
shape.
"""

from pathlib import Path

from module_registry import ModuleManifest


def _get_router():
    from module_packages.chat.backend.router import router

    return router


def m025_mark_chat_installed_unconditionally(brain: Path) -> None:
    """Chat was never optional — same no-existence-guard shape as tasks'
    own m021, since a locked (uninstallable=True) module must always be
    installed, on a brand-new instance exactly as much as an upgrading
    one. Confirmed chat truly had no config-style double-gate the way Home
    Assistant did before converting: is_ai_configured() is checked inline
    by 2 of 11 endpoints as a soft 200-with-error-message fallback, never a
    hard block on the module itself, and has zero effect on tool
    visibility — unlike HA's is_configured(), which gated 8 endpoints AND
    filtered _get_tools()'s output. Chat's own module gate has always been
    unconditional; this migration just makes that fact durable."""
    from services import mod_store_service
    from services.file_service import brain_path

    if brain != brain_path():
        return  # test/alternate brain root — mod_store_service always reads the live one

    mod_store_service.mark_installed("chat", by="migration:m025")


MODULE = ModuleManifest(
    id="chat",
    display_name="AI Chat",
    description="Talk to your LogCore AI — it reads your Brain and, with your approval, can make changes for you.",
    icon="◈",
    version="1.0.0",
    router_prefix="/api/v1/chat",
    router_tags=["chat"],
    get_router=_get_router,
    uninstallable=True,
    owned_brain_paths=["Chats"],
    owned_agent_tools=[],
    owned_block_types=[],
    migrations=[
        (
            "chat:m025_mark_chat_installed_unconditionally",
            m025_mark_chat_installed_unconditionally,
        ),
    ],
    help_section={
        "id": "chat",
        "icon": "💬",
        "title": "AI Chat",
        "blurb": "Talk to your LogCore AI. It can read your Brain (tasks, notes, journal, priorities, and more) and, with your approval, make changes for you — including building your Dashboards.",
        "howto": [
            'Type what you need — "plan my week", "summarize my month", "add three tasks for the move", "build me a dashboard for my house search", or "how do I use Finance?"',
            "Approve mode (the default): the AI reads freely but pauses for your OK before any change — approving replays exactly what was shown, never something re-guessed.",
            "If something's ambiguous, the AI can ask you a quick multiple-choice question right in the chat instead of guessing — pick an option (or a few) to continue.",
            "Switch modes with the selector — Plan proposes a plan first, Auto acts directly, Research adds web search (read-only).",
            "Use the 🧠 / ⏳ / 📚 buttons to save what matters to the AI's long-term or short-term memory.",
            "Chats auto-save; reopen a past chat to continue it.",
        ],
        "tips": [
            "Stuck on any feature? Just ask — the AI reads this Help guide and will explain it and link you to the right section.",
            "In Approve mode, nothing is changed until you click Approve, so it's safe to let it try things.",
            "It can find and work with notes shared with you too, not just your own — respecting whatever access level (read/contribute/edit) you were actually given.",
            "Ask it to add or change a Dashboard block and you'll see a live preview of your actual dashboard with the change applied, right in the chat, before you approve.",
            "Your message is saved the instant you send it, so it's never lost even if you close the app or lose connection before the reply comes back.",
        ],
        "modules": ["chat"],
    },
)
