# LogCore OS — Backlog

Items that are real but deferred. Review each before closing.

---

## Bugs

*None currently tracked.*

---

## Deferred Features

- **Projects module** — project tracking with tasks, milestones, and status (deferred to Phase 2 planning)
- **Multi-day calendar events** — calendar currently only supports single-day items via `due_date`. True events (vacations, trips, blocks) need an `end_date` field on tasks (or a separate events data type), a backend schema update, and a calendar renderer that spans cells across a date range. Design question: extend tasks with `end_date`, or introduce a dedicated event type separate from tasks?
