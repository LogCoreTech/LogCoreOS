# Phase 2: AI Operating Layer — Work Items

Five items to build, worked through systematically.

---

## Item 1: File Modification from Chat
Allow the AI agent to write back to Brain files during a chat session — tasks, notes, journal entries, goals, profile details, calendar events — when the user asks it to.

**Status:** Complete

New agent tools: `list_notes`, `create_note`, `update_note`, `delete_note`, `get_profile`, `update_profile`, `append_memory`. System prompt updated to clarify goals = tasks[type=goal], calendar = tasks[type=appointment].

**Extended (same item):** Added `rewrite_memory`, `get_task_history`, `search_brain`, `move_note`, `create_note_folder`, `create_tasks`, `send_notification`, `update_timezone`, `complete_shared_task` (user + assigned member), `update_shared_task` (admin), `delete_shared_task` (admin), `read_system_file` (admin), `update_system_file` (admin). Total: 29 user tools + 7 admin tools.

---

## Item 2: Long-Term Memory Writes from the App
Let the AI save things to `Long_Term_Memory.md` and `Short_Term_Memory.md` directly from the chat interface (currently only possible via CLI).

**Status:** Complete

Delivered as part of Item 1 extended toolset: `append_memory` writes to Short-Term Memory; `rewrite_memory` replaces the full memory file. Both tools are available to the agent in every chat session.

---

## Item 3: Planning Abilities
Natural language planning commands: "Plan my week", "Break this goal into tasks", "Organize my tasks by project", "Summarize my progress this month."

**Status:** Complete

Implemented propose-before-execute planning mode (`feat: planning abilities with propose-before-execute mode`) and auto mode where the AI executes without a confirmation step (`feat: add auto mode`). Mode is selectable in the chat UI.

---

## Item 4: Proactive Suggestions
AI surfaces suggestions based on Brain context — overdue items, goal drift, patterns — without the user asking.

**Status:** Complete

Per-user suggestion config, notification inbox, notification bell in the sidebar, and four built-in suggestion types (daily_digest, overdue_alert, weekly_review, goal_drift). Custom AI-powered suggestions configurable via agent tool `create_custom_suggestion`. Delivered in `feat: Phase 2 Item 4`.

---

## Item 5: Research Assistance
AI can gather, summarize, and store research into the Brain on command.

**Status:** Complete

Research mode added to the chat UI with Tavily web search integration. The agent can search the web, summarize results, and store them as notes in the Brain. Requires `TAVILY_API_KEY` in `.env`. Delivered in `feat: Phase 2 Item 5`.
