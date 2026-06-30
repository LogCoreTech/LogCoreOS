# LogCoreOS — In-App AI Agent

This directory documents the in-app LogCore AI agent: its architecture, available tools, operating modes, and brain skills.

The agent is implemented in `app/backend/services/agent_service.py` and exposed via `app/backend/routers/chat.py`.

For dev-session Claude Code tools (diagnose, run-tests, run-agent CLI), see `docs/skills/`.

---

## Operating Modes

| Mode | Behavior |
|------|----------|
| **Plan** | AI proposes a structured plan before executing. User approves or redirects. |
| **Auto** | AI executes directly using available tools (read/write Brain files, manage tasks, etc.). |
| **Research** | Read-only operations + web search via Tavily. No writes. |

---

## Tool Registry

Tools are defined in `agent_service.py` in two lists: `_USER_TOOLS` (available to all users) and `_ADMIN_TOOLS` (admin-only).

### Task Tools
`list_tasks`, `add_task`, `update_task`, `delete_task`, `create_tasks` (batch), `get_top3_tasks`, `get_scored_tasks`, `complete_shared_task`

### Brain File Tools
`list_brain_files`, `read_brain_file`, `write_brain_file`, `create_brain_file`, `search_brain`

### Memory Tools
`append_memory` (short/long-term), `rewrite_memory` (compress/clean)

### Notes Tools
`create_note`, `update_note`, `delete_note`, `list_notes`, `move_note`, `create_note_folder`

### Journal Tools
`read_journal_entry`, `write_journal_entry`, `list_journal_entries`

### Profile & History
`get_profile`, `update_profile`, `get_task_history`, `get_week_snapshot`

### Planning Tools
`propose_plan` (get approval before write actions)

### Suggestions Tools
`run_suggestion`, `update_suggestion`, `create_suggestion`

### Home Automation (conditional — only when HA is configured)
`get_home_state`, `control_home_device`, `activate_scene`, `trigger_home_automation`

### Web & Notifications
`search_web` (research mode only), `send_notification`, `update_timezone`

### Admin-Only Tools
`list_users`, `list_shared_tasks`, `add_shared_task`, `update_shared_task`, `delete_shared_task`, `read_system_file`, `update_system_file`, `run_tests`

---

## Brain Skills

Brain skills are reusable AI logic modules. They live in `brain/skills/` — the in-app AI reads them at runtime (via `brain/MEMORY_MAP.md`). Do not move skill files out of `brain/skills/`; the in-app AI depends on that path.

For reference, `agent/skills/` contains pointer files describing each skill. The authoritative source is always `brain/skills/`.

| Skill | What it does |
|-------|-------------|
| `life-priorities` | Scores tasks by the user's life priority hierarchy (God → Family → Job → Growth → Hobbies) and surfaces the top 3. Formula: `(category_weight × priority_weight) + urgency_bonus`. |

---

## Adding a Brain Skill

1. Create `brain/skills/<skill-name>/skill.md` — instructions, schema, AI rules
2. Add any helper scripts (`*.sh`) alongside it
3. Register it in `brain/MEMORY_MAP.md` under the Skills section
4. Add a pointer entry in `agent/skills/<skill-name>/README.md`
5. Update this README's skill table
