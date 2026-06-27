# Changelog

All notable changes to LogCore OS are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

---

## [0.1.0] — 2026-06-27

### Added

**Core platform**
- FastAPI backend with JWT authentication, bcrypt passwords, and JTI revocation
- React 18 / Vite / Tailwind CSS frontend, installable as a PWA
- Docker Compose stack with automated health checks
- `launch.sh` one-command startup script with `--install-deps` flag for automatic prerequisite installation on Linux

**AI**
- AI chat with full Brain context injection (priorities, tasks, memory, profile)
- Tool use support within chat
- Automatic chat archiving to Brain files
- Anthropic API integration via pluggable `ai_provider` abstraction

**Modules**
- Tasks — personal task management with life-priority scoring, recurring tasks, streak tracking, and history archival
- Notes — folder-based note editor with auto-save
- Journal — daily entries by date
- Calendar — personal events and dated task view
- Household — shared tasks and events across all household members with admin controls

**Scheduler**
- Nightly recurring task processor and history archival
- Configurable morning digest and overdue notifications via ntfy
- Weekly review summary

**Admin**
- User management
- AI provider settings
- Web search toggle
- Runtime hosting configuration (domain, HTTPS, proxy headers) — no restart required

**User settings**
- Accent colour, dark mode, background image, density, corner style
- Timezone
- Push notification subscription
- Session management

**Data portability**
- All user data stored as Markdown and JSON files in `brain/`
- Brain export as zip download
- No database — the filesystem is the database
