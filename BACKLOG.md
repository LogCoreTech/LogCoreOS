# LogCore OS — Backlog

Items that are real but deferred. Review each before closing.

---

## Bugs

### `_household` tasks not initialised
**Logged:** 2026-06-19  
**Severity:** Low  
**Files:** `app/backend/services/agent_service.py`, `app/backend/services/task_service.py`

The `_household` user (used by admin shared-task agent tools) has no brain folder and no `tasks.json`. Calling `list_shared_tasks` or `add_shared_task` via the agent returns a tool error until the file is manually created.

**Fix options:**
1. Seed `brain/USERS/_household/Tasks/tasks.json` as an empty `{"tasks": []}` alongside the existing `_template` — the simplest fix.
2. Have `task_service.add_task` create the file if absent (change `read_json(path)` → `read_json(path, default={"tasks": []})` in `add_task` and `list_tasks`).

Option 1 is preferred — keeps `task_service` simple and the issue is isolated to the household user.

---

## Deferred Features

- **Journal service** — backend CRUD + agent tools (deferred from agent plan, 2026-06-19)
- **Calendar service** — backend CRUD + agent tools (deferred from agent plan, 2026-06-19)
- **Obsidian-style Notes module** — frontend markdown editor for `Notes/` brain folder (deferred from agent plan, 2026-06-19)
