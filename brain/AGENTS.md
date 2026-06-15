# AGENTS.md — LogCore Brain Boot Protocol

This file is the single source of truth for how any AI agent should behave in this system.
All provider-specific files (CLAUDE.md, etc.) are thin redirects here.

---

## 1. Session Start — Read These First

Before doing anything else, read in this order:

1. `SOUL.md` — who you are, your personality and principles
2. `USERS.md` — who you're helping; ask at session start if unclear
3. `Memory/Long_Term_Memory.md` — system-wide stable knowledge (infrastructure, mission, design rules)
4. `USERS/{active_user}/Long_Term_Memory.md` — this user's personal stable knowledge
5. `USERS/{active_user}/Short_Term_Memory.md` — this user's recent active context
6. `USERS/{active_user}/Tasks/tasks.json` — this user's active tasks
7. `MEMORY_MAP.md` — navigation index for all memory files, skills, and plugins

Don't ask permission. Just do it. This is how you maintain continuity between sessions.

After reading tasks, score them using the life-priorities skill and surface the **top 3 most pressing tasks** at the start of the session.

---

## 2. Skills, Plugins, and Scripts

**Skills** live in `skills/`. Each skill has its own folder with a `skill.md` and any supporting scripts. Before doing repetitive work, check MEMORY_MAP.md to see if a skill already exists for it.

**When building a new skill:** Always read `skills/skill-creator/skill.md` first and follow its process.

**Vendor-agnostic design rule:** All logic, skills, and plugins live in the Brain. Provider-specific configs are thin wrappers that call into the Brain. If the AI provider changes, the Brain comes with you.

---

## 3. Memory — How to Keep It Updated

**The Golden Rule: Write it down. Never keep mental notes. Files survive session restarts. Memories don't.**

| When this happens | Do this |
|-------------------|---------|
| Something new or relevant is learned | Update the active user's `Short_Term_Memory.md` |
| System-wide fact changes | Update `Memory/Long_Term_Memory.md` |
| Real work is done in a session | Update `Memory/Daily Notes/YYYY-MM-DD.md` (create if missing) |
| Work happens on a specific project | Update relevant project memory file |
| Given a significant rule or pattern to follow | Write it to the active user's `Long_Term_Memory.md` |
| A new file is added to any memory folder | Add it to `MEMORY_MAP.md` |

**Memory split:**
- `Memory/Long_Term_Memory.md` — system-wide facts (mission, infrastructure, design rules)
- `USERS/{name}/Long_Term_Memory.md` — personal stable knowledge for that user
- `USERS/{name}/Short_Term_Memory.md` — personal active context for that user

---

## 4. Life Priorities — Task Management

Each user has a life priority hierarchy defined in their `Profile.md` (e.g., God → Family → Job → LogCore → Hobbies). Tasks are scored by category weight, urgency, and priority to surface the top 3 most important things to act on right now.

See `skills/life-priorities/skill.md` for the full scoring logic and instructions.

When a user asks "what should I focus on?" or at session start — score and surface their top 3.

---

## 5. End-of-Turn Memory Check

After every turn where real work was done:

1. Active user's `Short_Term_Memory.md` — update if anything new was learned or context changed
2. `Memory/Daily Notes/YYYY-MM-DD.md` — update if real work was done; create if missing
3. Any relevant project memory file — update if project work happened

Skip only if the turn was purely Q&A with no files changed and no decisions made.

---

## 6. Safety

- Don't share private information outside this system
- Don't run destructive commands without asking
- When in doubt, ask
