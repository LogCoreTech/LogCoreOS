# TASKS.md — LogCoreOS Active Work Queue

Keep this up to date. Mark tasks done as they're completed. Add new tasks as they surface. This is the single source of truth for what's being worked on.

---

## Active Tasks

*(nothing in flight)*

---

## Backlog

- [ ] **Projects module** — project tracking with tasks, milestones, and status (deferred to Phase 3+)
- [ ] **Multi-day calendar events** — calendar events currently support a single `date` field; true multi-day events (vacations, trips, blocks) need `start_date` / `end_date`, a backend schema update, and a calendar renderer that spans cells
- [ ] **Household task assignment for non-admins** — only admins can currently assign tasks because `GET /auth/users` is admin-gated; a `/shared/members` endpoint could expose the member list to all household members, enabling peer assignment
- [ ] **Personal calendar task completion toggle** — tasks shown in CalendarGrid day detail panel have no done/undo button; must navigate to Tasks page to un-mark done
- [ ] **Projects / chat system evolution** — evolve chat into a ChatGPT/Claude-style Projects feature: named projects with custom context, per-project chat archives, optional agent usage within each project

---

## Done

*(tracking starts from here — see git log for earlier history)*

---

## Format

```
- [ ] Task name — short description of what done looks like
- [x] Completed task — what was done (YYYY-MM-DD)
```
