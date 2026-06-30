# Brain Skill: Life Priorities

Scores a user's tasks by their life priority hierarchy (God → Family → Job → Personal Growth → Hobbies) and surfaces the top 3 most pressing tasks. Also manages recurring task logic and daily priority overrides.

**Source:** `brain/skills/life-priorities/skill.md` — the in-app AI reads it from there at runtime.

**Backend implementation:** `app/backend/services/priority_service.py` (`score_task`, `get_top3_tasks`)
