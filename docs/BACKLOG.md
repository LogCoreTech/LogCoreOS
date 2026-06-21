# LogCore OS — Backlog

Items that are real but deferred. Review each before closing.

---

## Bugs

*None currently tracked.*

---

## Deferred Features

- **Calendar UI** — backend and events CRUD API are complete (`routers/calendar.py`). The frontend page (`pages/Calendar.jsx`) needs to be built: month/week grid, event display with colors, create/edit modal, household pool view.
- **Projects module** — project tracking with tasks, milestones, and status (deferred to Phase 3+)
- **Multi-day calendar events** — calendar events currently support a single `date` field. True multi-day events (vacations, trips, blocks) need a `start_date` / `end_date` pair, a backend schema update, and a calendar renderer that spans cells. Design question: extend the existing event type or introduce a dedicated multi-day event type?
