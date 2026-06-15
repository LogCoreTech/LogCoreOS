# MEMORY MAP

Navigation index for the LogCore Brain. Use this to find what you need without loading everything.
When a new file is added to any folder, add a line here.

---

## Core System Files (load every session)

| File | What it contains |
|------|-----------------|
| `SOUL.md` | Agent personality, principles, communication style |
| `AGENTS.md` | Boot protocol — session start order, memory rules, life priority instructions |
| `USERS.md` | User registry and selection logic |
| `Memory/Long_Term_Memory.md` | System-wide stable knowledge: mission, infrastructure, design rules |

---

## Skills

| Folder | Skill | Purpose |
|--------|-------|---------|
| `skills/life-priorities/` | Life Priorities | Scores tasks by life priority hierarchy; surfaces top 3; manages task files per user |
| `skills/skill-creator/` | Skill Creator | Instructions and template for creating new skills |

---

## User Profiles & Memory

Each user has a personal folder under `USERS/`. Load these after identifying the active user.

| Path pattern | What it contains |
|-------------|-----------------|
| `USERS/{name}/{name}_Profile.md` | Personal info, priority order, preferences |
| `USERS/{name}/Long_Term_Memory.md` | Personal stable knowledge and AI behavior rules |
| `USERS/{name}/Short_Term_Memory.md` | Personal active context, current focus, follow-up queue |
| `USERS/{name}/Tasks/tasks.json` | Active tasks (source of truth) |
| `USERS/{name}/Tasks/tasks_history.json` | Completed / skipped non-recurring tasks |
| `USERS/{name}/Tasks/tasks_view.md` | Auto-generated human-readable task view |
| `USERS/{name}/Tasks/daily_override.json` | Optional: today's priority order override |

---

## Daily Notes

Location: `Memory/Daily Notes/YYYY-MM-DD.md`

One file per session day. Load today's and yesterday's at session start.

| File | Summary |
|------|---------|
| *(none yet)* | — |

---

## System Memory

| File | What it contains |
|------|-----------------|
| `Memory/Long_Term_Memory.md` | System-wide stable facts (mission, infrastructure, design constraints) |
