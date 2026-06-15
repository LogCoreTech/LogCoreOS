# Long-Term Memory — System Wide

This file contains stable, system-wide knowledge. Personal user knowledge lives in each user's own Long_Term_Memory.md.

---

## LogCore OS — Mission

A self-hosted, values-driven family life operating system with an AI that knows you personally. Built around your priorities, not generic productivity advice.

Two products:
- **LogCore Brain (free/open source):** Markdown + JSON file architecture. Works with any AI.
- **LogCore App (paid/hosted):** Python FastAPI + React PWA. Dashboards, task management, AI chat, scheduling, notifications.

---

## Design Rules

- **Vendor-agnostic:** All logic lives in the Brain files. Provider-specific configs (CLAUDE.md, etc.) are thin redirects. If the AI provider changes, the Brain comes with you.
- **Files are the source of truth:** tasks.json, Profile.md, memory files — these are the data. The app reads and writes them. The AI reads them directly.
- **Memory split:** System-wide facts → this file. Personal context → user's own Long_Term_Memory.md.
- **Don't use Claude's auto-memory:** All memory belongs in Brain files only.

---

## Infrastructure

*(Fill in when deployed — server details, URLs, stack info)*
