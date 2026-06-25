# LogCore OS — Backlog

Items that are real but deferred. Review each before closing.

---

## Bugs

*None currently tracked.*

---

## Deferred Features

- **Projects module** — project tracking with tasks, milestones, and status (deferred to Phase 3+)
- **Multi-day calendar events** — calendar events currently support a single `date` field. True multi-day events (vacations, trips, blocks) need a `start_date` / `end_date` pair, a backend schema update, and a calendar renderer that spans cells. Design question: extend the existing event type or introduce a dedicated multi-day event type?
- **Household task assignment for non-admins** — currently only admins can assign tasks (because the user list endpoint `GET /auth/users` is admin-gated). A `/shared/members` endpoint could expose the household member list to all members, enabling any member to assign tasks.
- **Personal calendar task completion toggle** — tasks shown in the CalendarGrid day detail panel have no done/undo button. Un-marking done from the calendar requires going to the Tasks page.
