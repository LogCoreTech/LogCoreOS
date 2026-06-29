# Plan: Phase 2 Item 1 — Agent File Modification Tools

## Goal
Allow the AI agent to write back to the user's Brain during chat — notes, profile details, goals, calendar appointments, journal, and memory — when the user asks it to.

## Current State
`agent_service.py` already has:
- Tasks: full CRUD (`list_tasks`, `add_task`, `update_task`, `delete_task`, etc.)
- Generic brain files: `list_brain_files`, `read_brain_file`, `write_brain_file`, `create_brain_file`
- Journal: `read_journal_entry`, `write_journal_entry`
- Admin: `list_users`, `list_shared_tasks`, `add_shared_task`

**What's missing:**
- Notes: generic brain file tools work but bypass `notes_service` path validation and folder logic
- Profile: no tools at all — agent can't read or update profile fields
- Goals: agent doesn't know goals are tasks with `type: 'goal'`
- Calendar: agent doesn't know appointments are tasks with `type: 'appointment'` + `due_date`
- Memory: write_brain_file can overwrite memory files but no safe append tool

---

## Step 1 — Add Notes Tools to `agent_service.py`

Add 4 dedicated note tools to `_USER_TOOLS`. They call `notes_service` directly, which has proper `_validate_path`, size limits, and folder support.

**New tools:**
- `list_notes` — calls `notes_service.list_notes(user["name"])`
- `create_note` — inputs: `path` (e.g. `"Work/Meeting Notes"`), `content`. Calls `notes_service.create_note`
- `update_note` — inputs: `path`, `content`. Calls `notes_service.update_note`. Returns error if not found.
- `delete_note` — inputs: `path`. Calls `notes_service.delete_note`.

Note reading is already covered by `read_brain_file` with path `Notes/Folder/Name.md`.

Add to `_execute_tool` match cases: `"list_notes"`, `"create_note"`, `"update_note"`, `"delete_note"`.

Import `notes_service` at the top of the file (already has `journal_service` as a pattern to follow).

---

## Step 2 — Add Profile Tools to `agent_service.py`

Add 2 profile tools to `_USER_TOOLS`. They call `profile_service`.

**New tools:**
- `get_profile` — no inputs. Returns full `profile.json` dict via `profile_service.load_profile`.
- `update_profile` — inputs: any subset of profile fields as a flat dict (patch-style). Load current profile, merge inputs into it, save via `profile_service.save_profile`. This regenerates `Profile.md` automatically.

Key profile fields the agent should know about (document in tool description):
`occupation`, `city`, `state`, `country`, `pronouns`, `wake_weekday`, `wake_weekend`, `bedtime`, `work_hours`, `height`, `weight`, `blood_type`, `diet`, `exercise`, `conditions`, `medications`, `employer`, `industry`, `education`, `years_experience`, `skills`, `marital_status`, `partner`, `children` (list of `{name, age}`), `pets`, `income_range`, `savings_goal`, `budget_style`, `life_mission`, `big_goal`, `core_values`, `key_constraints`, `communication_style`, `tone`, `response_language`, `topics_to_emphasize`, `topics_to_avoid`, `notes`, `priority_order` (list of strings).

Add to `_execute_tool`: `"get_profile"`, `"update_profile"`.

Import `profile_service` at the top.

---

## Step 3 — Add `append_memory` Tool to `agent_service.py`

A safe, append-only tool for memory files. Better than `write_brain_file` for memory because it can't accidentally wipe existing entries.

**New tool:**
- `append_memory` — inputs: `content` (markdown text to append), `target` (enum: `"short"` | `"long"`, default `"short"`). Reads the current memory file, appends `\n\n## {today}\n\n{content}`, writes back atomically. Respects the 100 KB cap from `_MEMORY_MAX_BYTES` (already defined in `chat.py` — move the constant to `file_service.py` or repeat it in `agent_service.py`).

Add to `_execute_tool`: `"append_memory"`.

---

## Step 4 — Update the System Prompt in `chat.py`

The current system prompt doesn't tell the AI that goals and calendar appointments are tasks. Update `_build_context` or the system prompt string in the `chat()` route to include:

```
- Goals are tasks with type='goal'. Use add_task/update_task/list_tasks to manage them.
- Calendar appointments are tasks with type='appointment' and a due_date (and optionally due_time). Use add_task/update_task to manage them.
- Notes live in the Notes/ folder. Use list_notes, create_note, update_note, delete_note.
- To update profile details (occupation, health, family, values, etc.), use get_profile then update_profile.
- To save something to memory, use append_memory.
```

This is a small addition at the end of the existing system_prompt string — no structural change to `_build_context`.

---

## Step 5 — Update `docs/PHASE2_PLAN.md`

Mark Item 1 as complete and add a short implementation note.

---

## Files Changed

| File | Change |
|------|--------|
| `app/backend/services/agent_service.py` | Add `list_notes`, `create_note`, `update_note`, `delete_note`, `get_profile`, `update_profile`, `append_memory` tools + executors. Import `notes_service`, `profile_service`. |
| `app/backend/routers/chat.py` | Extend system prompt string with tool guidance for goals, calendar, notes, profile, memory. |
| `docs/PHASE2_PLAN.md` | Mark Item 1 complete. |

No new files. No schema migrations. No frontend changes needed — agent responses already surface in the chat UI.

---

## What This Does NOT Cover (remaining Phase 2 items)
- Long-term memory writes from the App (Item 2) — `append_memory` tool covers the write side; the full "App-initiated save" UX is separate
- Planning abilities (Item 3)
- Proactive suggestions (Item 4)
- Research assistance (Item 5)
