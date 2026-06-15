# Skill: Life Priorities

Scores a user's tasks by their life priority hierarchy and surfaces the top 3 most pressing tasks. Manages task files, recurring task logic, and daily priority overrides.

---

## Purpose

Life gets busy. This skill ensures the most important things — based on what the user has said matters most to them — always surface first. It replaces "what should I do?" with a clear, values-aligned answer.

---

## Life Priority System

Each user defines their priority order in their `Profile.md` under `## Life Priorities`. The base categories are:

- God
- Family
- Job
- Personal Growth
- Hobbies

Users can add custom categories and reorder to match their actual values.

**Daily override:** If `Tasks/daily_override.json` exists with today's date, use that order instead of the profile order for the current day.

---

## Scoring Formula

```
category_weight = (total_categories - position_index)  # position 0 = highest weight
priority_weight: High=3, Medium=2, Low=1
urgency_bonus:  overdue=10, due_today=5, due_this_week=2, no_due_date=0

final_score = (category_weight × priority_weight) + urgency_bonus
```

Top 3 = the 3 highest-scoring tasks with `status: pending`.

---

## Task Schema (tasks.json)

```json
{
  "tasks": [
    {
      "id": "uuid-v4",
      "title": "Read Bible for 30 minutes",
      "category": "God",
      "priority": "High",
      "type": "recurring",
      "recurrence": "daily",
      "due_date": "2026-06-14",
      "status": "pending",
      "created_at": "2026-06-14T08:00:00-05:00",
      "completed_at": null,
      "notes": null,
      "streak_count": 7,
      "last_completed_date": "2026-06-13"
    }
  ]
}
```

**Field values:**
- `category`: any string from the user's active category list
- `priority`: `High | Medium | Low`
- `type`: `todo | recurring | goal | appointment`
- `recurrence`: `null | daily | weekly | monthly`
- `due_date`: ISO date string or `null`
- `status`: `pending | done | skipped`
- `streak_count`: integer, meaningful only for recurring tasks
- `last_completed_date`: ISO date or `null`

---

## Recurring Task Logic

**When a recurring task is marked done:**
- Set `status: done`, `completed_at: now`, `last_completed_date: today`
- Increment `streak_count` by 1
- The recurring processor (runs nightly) will advance the `due_date` and reset status to `pending`

**Nightly recurring processor:**
- For each recurring task where `status == done` and `last_completed_date == today`: advance `due_date` to next occurrence, reset `status` to `pending`
- For each recurring task where `status == pending` and `due_date < today`: reset `streak_count` to 0, advance `due_date` to today (broken streak)

---

## Daily Override

File: `USERS/{name}/Tasks/daily_override.json`

```json
{
  "date": "2026-06-14",
  "order": ["Job", "God", "Family", "Personal Growth", "Hobbies"]
}
```

The app provides a "Reorder Today" button that writes this file. The AI can also apply a verbal session override: "today put Job first" — apply that order for the current session without writing the file.

---

## AI Instructions

### At session start:
1. Read `USERS/{active_user}/Tasks/tasks.json`
2. Read the user's priority order from their `Profile.md ## Life Priorities` section
3. Check `Tasks/daily_override.json` — if date matches today, use that order instead
4. Apply the scoring formula to all `pending` tasks
5. Surface the top 3 with a brief explanation of why they rank highest

### Adding a task:
1. Generate a UUID for the `id`
2. Ask for: title, category (from their list), priority, type, optional due date, optional notes
3. Append to `tasks.json`
4. Re-run `render_view.sh` if using the CLI path, or the app handles this automatically

### Marking a task done:
1. Update `status: done`, `completed_at: now`
2. If recurring: set `last_completed_date: today`, increment `streak_count`
3. If non-recurring: move the task from `tasks.json` to `tasks_history.json`

### When asked "what should I focus on?":
Score and surface top 3. Be concise — list them with category and a one-line reason.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `score_tasks.sh` | Reads tasks.json + profile priority order, outputs scored top 3 + full ranked list |
| `render_view.sh` | Generates tasks_view.md from tasks.json — grouped by category, then priority |

---

## How to Invoke

### Any AI (manual)
Read tasks.json and the user's Profile.md priority section. Apply the scoring formula above. Surface top 3.

### LogCore App (automated)
The Python backend (`priority_service.py`) implements this scoring logic. The app calls `/api/tasks/top3` which runs the scoring and returns results. The dashboard displays top 3 automatically.

### CLI (scripts)
```bash
bash "skills/life-priorities/score_tasks.sh" "User Name"
bash "skills/life-priorities/render_view.sh" "User Name"
```
Requires `jq` installed on the host.
