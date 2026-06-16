# LogCoreOS — Project Documents

*Combined reference: System Architecture + Development Roadmap.*

---

# Part 1 — System Architecture

## Vision

LogCoreOS is a self-hosted, open-source, AI-native life operating system that acts as the central intelligence and data layer for an individual or family.

The core principles:

- Data ownership first
- Human-readable files first
- Vendor agnostic
- Local-first with cloud convenience options
- AI as an interface, not the product
- Extensible and modular

---

## Two Products

**LogCore Brain** (`brain/`) — Free and open source. Markdown and JSON files. Works with any AI — Claude Code, GPT, Ollama, anything. Take your Brain folder anywhere and your AI context comes with you.

**LogCore App** (`app/`) — The software layer. Python FastAPI backend + React frontend, installable as a PWA on phones and desktops. Dashboards, task management, integrated AI chat, background scheduling, push notifications. This is what you run (or pay to have hosted).

---

## High-Level Architecture

```
User Interface (React PWA)
      ↓
Application Layer (FastAPI)
      ↓
AI Agent Layer (Brain context → Anthropic API)
      ↓
The Brain (Source of Truth — Markdown + JSON files)
      ↓
Automation Layer (Scheduler / future: n8n)
      ↓
External Services & Devices
```

---

## 1. The Brain

The Brain is the heart of LogCoreOS.

All user data exists as organized Markdown and JSON files inside `brain/`. The Brain is fully portable — it works with any AI out of the box. If the AI provider changes, the Brain comes with you.

Structure:

```
brain/
├── AGENTS.md              ← AI boot protocol (session start order, memory rules)
├── SOUL.md                ← AI personality and communication principles
├── USERS.md               ← User registry and selection logic
├── MEMORY_MAP.md          ← Navigation index for all memory files, skills, plugins
├── Memory/
│   ├── Long_Term_Memory.md    ← System-wide stable knowledge
│   └── Daily Notes/           ← One file per session day (YYYY-MM-DD.md)
├── USERS/
│   ├── _template/             ← Copied for each new user at setup
│   │   ├── Profile.md
│   │   ├── Long_Term_Memory.md
│   │   ├── Short_Term_Memory.md
│   │   └── Tasks/
│   │       ├── tasks.json
│   │       ├── tasks_history.json
│   │       ├── tasks_view.md
│   │       └── daily_override.json
│   └── {User Name}/           ← Created by the setup wizard on first login
└── skills/
    ├── life-priorities/       ← Task scoring + recurring task logic
    └── skill-creator/         ← Template and process for building new skills
```

The Brain files are the permanent source of truth. Databases exist only as generated indexes for search, caching, or performance.

---

## 2. AI Agent System

The AI agent is the operating interface for LogCoreOS.

At the start of every session, the AI reads the Brain in this order:

1. `SOUL.md` — personality and principles
2. `USERS.md` — who is being helped
3. `Memory/Long_Term_Memory.md` — system-wide stable knowledge
4. `USERS/{name}/Long_Term_Memory.md` — personal stable knowledge
5. `USERS/{name}/Short_Term_Memory.md` — recent active context
6. `USERS/{name}/Tasks/tasks.json` — active tasks
7. `MEMORY_MAP.md` — navigation index

After loading, the agent scores the user's tasks and surfaces the **top 3 most pressing tasks** using the Life Priorities skill.

Current AI provider: Anthropic (configurable via `AI_MODEL` environment variable). Multi-provider support (local models, OpenAI, Ollama) is a planned roadmap item.

---

## 3. Life Priority Scoring

The Life Priorities skill is a core built-in feature.

Each user defines their priority order in `Profile.md` (e.g., God → Family → Job → Personal Growth → Hobbies). Tasks are scored by category weight, urgency, and priority to surface what matters most right now.

**Scoring formula:**

```
category_weight = total_categories - position_index
priority_weight: High=3, Medium=2, Low=1
urgency_bonus:  overdue=10, due_today=5, due_this_week=2, no_due_date=0

final_score = (category_weight × priority_weight) + urgency_bonus
```

Implemented in both the AI layer (`skills/life-priorities/`) and the App backend (`priority_service.py`). The dashboard displays top 3 automatically via `/api/tasks/top3`.

---

## 4. Application Modules

The App currently provides:

**Active (Phase 1):**

- User authentication
- Task management (create, complete, skip, recurring)
- Life priority scoring and top-3 dashboard
- AI chat interface (Brain context injected into every message)
- Push notifications via ntfy
- Setup wizard (creates user Brain folder from template)
- Background scheduler (nightly recurring task processor)

**Planned:**

- Notes
- Journal
- Projects
- Calendar
- Health tracking
- Home automation
- Research tools

---

## 5. Multi-User Architecture

Multi-user is foundational from Phase 0, not a later addition.

One installation supports a single person, couple, family, or household.

Each user receives:

- Their own `USERS/{name}/` Brain folder
- Private memory and tasks
- Individual AI preferences (defined in their Profile)
- Individual life priority hierarchy

Shared spaces and family-level features are planned for a later phase.

---

## 6. Automation System

**Current:** A Python scheduler (`scheduler.py`) runs nightly to advance recurring tasks, reset streaks for broken habits, and trigger push notifications.

**Planned (Phase 3):** n8n as a visual automation engine for user-defined workflows, event triggers, and smart home control. The custom scheduler may coexist with n8n for internal task processing.

---

## 7. Integration Layer

Planned connectors:

- Calendars
- Email
- Cloud storage
- Health devices
- Smart home systems
- Messaging platforms
- Financial services
- External APIs

---

## 8. Deployment

**Tech stack:**

- Backend: Python FastAPI
- Frontend: React + Vite + Tailwind CSS (served as PWA)
- Notifications: ntfy (self-hosted)
- Containers: Docker Compose

**Docker services:**

```
logcore-app    → FastAPI backend + React frontend (port 8000)
logcore-ntfy   → ntfy push notification server (port 5680)
```

The `brain/` folder is mounted as a volume — all Brain files persist outside the container.

**Deployment models:**

- **Community:** Self-hosted via Docker Compose. Free, full data ownership.
- **Managed:** LogCore hosted. Automatic backups, easy updates, remote access. *(planned)*
- **Appliance:** Dedicated hardware with LogCoreOS pre-installed. *(planned)*

---

# Part 2 — Development Roadmap

## Phase 0: Foundation ✅ Complete

Create the Brain standard.

Done:

- Brain folder structure (`AGENTS.md`, `SOUL.md`, `USERS.md`, `MEMORY_MAP.md`, `Memory/`, `USERS/_template/`)
- Per-user memory system (Profile, Long-Term Memory, Short-Term Memory)
- Life Priorities skill (`skills/life-priorities/`) with scoring formula, task schema, recurring logic
- Skill-creator system for building new skills
- AI boot protocol and end-of-turn memory rules

---

## Phase 1: Core MVP 🔄 In Progress

**Goal:** A usable personal life operating system.

Done:

- User authentication
- Setup wizard (creates user from template)
- Task management (CRUD, recurring, streaks, history)
- Life priority scoring (top 3 dashboard)
- AI chat interface with full Brain context injection
- Push notifications (ntfy)
- Background scheduler (nightly recurring task processor)
- React PWA (installable on phone and desktop)
- Docker Compose deployment

Still to build:

- Notes
- Journal
- Projects
- Basic calendar

---

## Phase 2: AI Operating Layer

Expand the agent with:

- Long-term memory writes from the App (not just CLI)
- Planning abilities
- Proactive suggestions
- File modification from chat
- Research assistance

Create a natural language command interface. Examples:

- "Plan my week."
- "Summarize my progress this month."
- "Organize my tasks by project."
- "Create a goal and break it into tasks."

---

## Phase 3: Automation

Integrate n8n alongside the existing scheduler.

Features:

- Visual automation editor
- AI-generated workflows
- Event triggers
- Notifications
- Device control

Clarify boundary between n8n (user-defined workflows) and the internal scheduler (Brain file processing).

---

## Phase 4: Integrations and Migration

Develop connectors:

- Existing note applications (Notion, Obsidian, Apple Notes)
- Calendar systems (Google, Apple)
- Task managers (Todoist, Things)
- Health platforms (Apple Health, Garmin)
- Smart home systems (Home Assistant)

Build AI-assisted migration:

- "Import my digital life."

The AI organizes everything into the Brain.

---

## Phase 5: Family Operating System

Build on the existing multi-user foundation:

- Shared spaces (family calendar, shared tasks)
- Permission controls (what each user can see)
- Family dashboard
- Shared shopping lists
- Chore management
- Household automation

---

## Phase 6: AI Provider Expansion

Deliver on the vendor-agnostic promise:

- Plug-in AI provider system
- Support for local models (Ollama, LM Studio)
- Support for OpenAI, Gemini, and other cloud providers
- Maintain the Brain-as-context-layer regardless of provider

---

## Phase 7: Ecosystem

Create:

- Plugin system
- Public Brain specification
- Developer API
- Community marketplace

---

## Phase 8: Commercial Platform

Launch:

- Managed hosting
- Enterprise-grade infrastructure
- Premium AI services
- Hardware appliance

---

## Development Philosophy

Do not begin by building every feature.

The first goal is to create the foundation:

```
Brain → AI Agent → Core Applications → Automations → Ecosystem
```

If the foundation is correct, every future feature becomes easier to build.

All logic, skills, and plugins live in the Brain. Provider-specific configs are thin wrappers. If the AI provider changes tomorrow, the Brain — and everything the user has built — comes with them.
