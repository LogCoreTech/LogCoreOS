"""Goals CRUD, hierarchy, and progress computation. Deliberately kept fully
inside this package (unlike task_service.py/assets_service.py/etc., which
all stay core because of real external consumers) — nothing outside this
package needs to import Goals data directly. A Goal doesn't participate in
the per-user share-handshake system Assets/Finance/Contacts/Notes use (no
shared_with/contributors on an individual goal), so
services/user_deletion_service.py needs no Goals-specific handling either —
a user's personal goals are deleted with the rest of their Brain folder,
same as their Tasks already are. Pool (household/team) goals live under the
existing `_household`/`_team` pseudo-users, exactly like pool tasks/events —
no separate pool store or separate router, just this same service pointed
at the pseudo-user's name.

Hierarchy mirrors assets_service.py's parent_id/collect_subtree_ids pattern
exactly (unbounded depth, cycle-guarded). Linked Tasks mirror the existing
asset_id field on Task — a plain FK field (goal_id), resolved by filtering,
no join table.
"""

import uuid
from datetime import datetime, date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from services.auth_service import get_user_timezone
from services.file_service import goals_path, goal_progress_history_path, read_json, update_json, write_json


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------


def list_goals(store_user: str, workspace: str = "personal") -> list[dict]:
    return read_json(goals_path(store_user, workspace), default={"goals": []}).get("goals", [])


def get_goal(store_user: str, goal_id: str, workspace: str = "personal") -> dict | None:
    return next((g for g in list_goals(store_user, workspace) if g["id"] == goal_id), None)


def _by_id(goals: list[dict]) -> dict[str, dict]:
    return {g["id"]: g for g in goals}


def collect_subtree_ids(goals: list[dict], root_id: str) -> set[str]:
    """Every id in root_id's own subtree (root included), cycle-safe — direct
    port of assets_service.py's own collect_subtree_ids()."""
    children: dict[str | None, list[str]] = {}
    for g in goals:
        children.setdefault(g.get("parent_id"), []).append(g["id"])
    out: set[str] = set()
    stack = [root_id]
    while stack:
        node = stack.pop()
        if node in out:
            continue
        out.add(node)
        stack.extend(children.get(node, []))
    return out


def create_goal(store_user: str, data: dict, workspace: str = "personal") -> dict:
    tz = ZoneInfo(get_user_timezone(store_user)) if not store_user.startswith("_") else ZoneInfo("UTC")
    now = datetime.now(tz).isoformat()

    parent_id = data.get("parent_id")
    if parent_id:
        existing = list_goals(store_user, workspace)
        if not any(g["id"] == parent_id for g in existing):
            raise ValueError(f"Parent goal {parent_id!r} not found")

    tags = [t.strip() for t in (data.get("tags") or []) if t and t.strip()]

    goal: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "title": data["title"],
        "notes": data.get("notes"),
        "category": data.get("category", ""),
        "parent_id": parent_id,
        "due_date": data.get("due_date"),
        "status": "pending",
        "metric": data.get("metric"),
        "tags": tags,
        "created_by": data.get("created_by"),
        "created_at": now,
        "updated_at": now,
    }

    def _add(store: dict) -> dict:
        store["goals"].append(goal)
        return store

    update_json(goals_path(store_user, workspace), _add, default={"goals": []})

    if tags:
        from services.tags_service import register_tags

        register_tags(store_user, workspace, tags)

    return goal


def update_goal(
    store_user: str, goal_id: str, updates: dict, workspace: str = "personal"
) -> dict | None:
    tz = ZoneInfo(get_user_timezone(store_user)) if not store_user.startswith("_") else ZoneInfo("UTC")
    found: dict | None = None
    error: str | None = None

    def _update(store: dict) -> dict:
        nonlocal found, error
        goals = store["goals"]
        by_id = _by_id(goals)
        for i, g in enumerate(goals):
            if g["id"] != goal_id:
                continue
            if "parent_id" in updates and updates["parent_id"] != g.get("parent_id"):
                new_parent = updates["parent_id"]
                if new_parent:
                    if new_parent not in by_id:
                        error = f"Parent goal {new_parent!r} not found"
                        return store
                    if new_parent in collect_subtree_ids(goals, goal_id):
                        error = "Cannot move a goal under itself or its own descendant"
                        return store
            goals[i] = {**g, **updates, "updated_at": datetime.now(tz).isoformat()}
            found = goals[i]
            break
        return store

    update_json(goals_path(store_user, workspace), _update, default={"goals": []})
    if error:
        raise ValueError(error)
    if found and updates.get("tags"):
        from services.tags_service import register_tags

        register_tags(store_user, workspace, updates["tags"])
    return found


def delete_goal(
    store_user: str,
    goal_id: str,
    workspace: str = "personal",
    cascade: bool = False,
    delete_linked_tasks: bool = False,
) -> dict | None:
    """Delete a goal per the owner's chosen scope. Returns None if not found,
    else {"deleted_goal_ids": [...], "affected_task_ids": [...]}.

    cascade=False: the goal's own subgoals are re-parented up to ITS parent
    (root-level if it had none) instead of being deleted.
    cascade=True: the whole subtree (this goal + every descendant) is deleted.

    delete_linked_tasks controls what happens to Tasks whose goal_id points
    at any of the deleted goal ids — True deletes them too, False (default)
    just clears goal_id so they stay as ordinary tasks, matching the
    existing precedent that nothing else in this app cascade-deletes a Task
    when the thing it's linked to goes away."""
    result: dict | None = None

    def _delete(store: dict) -> dict:
        nonlocal result
        goals = store["goals"]
        by_id = _by_id(goals)
        target = by_id.get(goal_id)
        if target is None:
            return store

        if cascade:
            to_delete = collect_subtree_ids(goals, goal_id)
            store["goals"] = [g for g in goals if g["id"] not in to_delete]
        else:
            to_delete = {goal_id}
            new_parent = target.get("parent_id")
            new_goals = []
            for g in goals:
                if g["id"] == goal_id:
                    continue
                if g.get("parent_id") == goal_id:
                    g = {**g, "parent_id": new_parent}
                new_goals.append(g)
            store["goals"] = new_goals

        result = {"deleted_goal_ids": sorted(to_delete)}
        return store

    update_json(goals_path(store_user, workspace), _delete, default={"goals": []})
    if result is None:
        return None

    from services import task_service

    affected_task_ids: list[str] = []
    all_tasks = task_service.list_tasks(store_user, workspace)
    for t in all_tasks:
        if t.get("goal_id") in result["deleted_goal_ids"]:
            affected_task_ids.append(t["id"])
            if delete_linked_tasks:
                task_service.delete_task(store_user, t["id"], workspace)
            else:
                task_service.update_task(store_user, t["id"], {"goal_id": None}, workspace)
    result["affected_task_ids"] = affected_task_ids
    return result


# ---------------------------------------------------------------------------
# Hierarchy helpers
# ---------------------------------------------------------------------------


def get_subgoals(store_user: str, goal_id: str, workspace: str = "personal") -> list[dict]:
    return [g for g in list_goals(store_user, workspace) if g.get("parent_id") == goal_id]


def get_root_goals(store_user: str, workspace: str = "personal") -> list[dict]:
    """Root-level (no parent) goals — the "ME" life-goals view."""
    return [g for g in list_goals(store_user, workspace) if not g.get("parent_id")]


def get_linked_tasks(store_user: str, goal_id: str, workspace: str = "personal") -> list[dict]:
    from services import task_service

    return [t for t in task_service.list_tasks(store_user, workspace) if t.get("goal_id") == goal_id]


# ---------------------------------------------------------------------------
# Manual metric — logged history
# ---------------------------------------------------------------------------


def log_manual_value(
    store_user: str, goal_id: str, value: float, workspace: str = "personal", when: str | None = None
) -> dict | None:
    """Append a dated {date, value} entry to a manual-metric goal's history.
    `when` defaults to today in the store's own timezone; pass an explicit
    date to backfill/correct an entry."""
    tz = ZoneInfo(get_user_timezone(store_user)) if not store_user.startswith("_") else ZoneInfo("UTC")
    entry_date = when or datetime.now(tz).date().isoformat()
    found: dict | None = None

    def _update(store: dict) -> dict:
        nonlocal found
        for g in store["goals"]:
            if g["id"] != goal_id:
                continue
            metric = g.get("metric") or {"provider": "manual", "config": {}}
            history = list(metric.get("history") or [])
            history = [e for e in history if e.get("date") != entry_date] + [
                {"date": entry_date, "value": value}
            ]
            history.sort(key=lambda e: e["date"])
            metric["history"] = history
            g["metric"] = metric
            g["updated_at"] = datetime.now(tz).isoformat()
            found = g
            break
        return store

    update_json(goals_path(store_user, workspace), _update, default={"goals": []})
    return found


# ---------------------------------------------------------------------------
# Progress computation — metric wins if configured, else weighted rollup of
# children, else manual pending/done toggle. Computed live on every call,
# same as finance_planning_service.budget_status()'s own precedent.
# ---------------------------------------------------------------------------


def _resolve_metric(metric: dict, user: dict, workspace: str) -> dict:
    """{"current": float, "target": float | None, "pct": int}. Never raises —
    a broken/missing provider degrades to 0%, not a crashed request."""
    provider = metric.get("provider")
    config = metric.get("config") or {}

    if provider == "manual":
        from module_registry import directional_pct

        history = metric.get("history") or []
        current = history[-1]["value"] if history else 0
        target = config.get("target_value")
        direction = config.get("direction", "increase")
        start_value = config.get("start_value")
        pct = directional_pct(current, target, direction, start_value)
        return {"current": current, "target": target, "pct": pct}

    from module_registry import metric_providers

    spec = metric_providers().get(provider)
    if spec is None:
        return {"current": 0, "target": None, "pct": 0}
    try:
        result = spec.resolve(config, user, workspace)
        pct = max(0, min(100, round(result.get("pct", 0))))
        return {"current": result.get("current", 0), "target": result.get("target"), "pct": pct}
    except Exception:
        return {"current": 0, "target": None, "pct": 0}


_COMPLETION_RATE_WINDOW_DAYS = 30


def recurring_completion_rate(task: dict) -> float:
    """A linked recurring task's own 30-day completion rate, automatically
    contributed to its parent goal's rollup instead of a binary done/not-done
    check — owner-requested (2026-08-29): "repeating tasks... have the
    metrics stored for them within the task itself... so there can be more
    collective data for a goal." Reads task_service.py's own completion_log
    (a dated entry per completion, capped at 90 — see that file). Fixed
    30-day window, not configurable, matching "automatic, no extra
    configuration step"."""
    log = task.get("completion_log") or []
    if not log:
        return 0.0
    cutoff = (date.today() - timedelta(days=_COMPLETION_RATE_WINDOW_DAYS)).isoformat()
    recent = sum(1 for e in log if e.get("date", "") >= cutoff)
    return max(0.0, min(100.0, recent * 100 / _COMPLETION_RATE_WINDOW_DAYS))


def compute_progress(
    store_user: str, goal: dict, workspace: str, user: dict, _goals: list[dict] | None = None
) -> dict:
    """{"pct": int, "source": "metric" | "rollup" | "manual", "current": ..., "target": ...}."""
    metric = goal.get("metric")
    if metric:
        resolved = _resolve_metric(metric, user, workspace)
        return {"source": "metric", **resolved}

    goals = _goals if _goals is not None else list_goals(store_user, workspace)
    subgoals = [g for g in goals if g.get("parent_id") == goal["id"]]

    from services import task_service

    linked_tasks = [t for t in task_service.list_tasks(store_user, workspace) if t.get("goal_id") == goal["id"]]

    children_pct: list[float] = []
    for sg in subgoals:
        children_pct.append(compute_progress(store_user, sg, workspace, user, goals)["pct"])
    for t in linked_tasks:
        if t.get("type") == "recurring":
            # Opt-in: a recurring task only moves the rollup once its own
            # counts_toward_goal flag is explicitly on (see task_service.py).
            if t.get("counts_toward_goal", True):
                children_pct.append(recurring_completion_rate(t))
        else:
            children_pct.append(100.0 if t.get("status") == "done" else 0.0)

    if children_pct:
        pct = round(sum(children_pct) / len(children_pct))
        return {"source": "rollup", "pct": pct, "current": None, "target": None}

    pct = 100 if goal.get("status") == "done" else 0
    return {"source": "manual", "pct": pct, "current": None, "target": None}


def on_pace(goal: dict, progress: dict) -> str | None:
    """"on_pace" / "behind_pace", or None if the goal doesn't have both a
    metric target_value and a due_date (there's nothing to project against).
    Straight-line interpolation from created_at to due_date."""
    metric = goal.get("metric") or {}
    target = progress.get("target")
    due = goal.get("due_date")
    created = goal.get("created_at")
    if progress.get("source") != "metric" or target in (None, 0) or not due or not created:
        return None
    try:
        start = date.fromisoformat(created[:10])
        end = date.fromisoformat(due)
        today = date.today()
    except ValueError:
        return None
    total_days = (end - start).days
    if total_days <= 0:
        return None
    elapsed = max(0, min(total_days, (today - start).days))
    expected = target * (elapsed / total_days)
    current = progress.get("current") or 0
    return "on_pace" if current >= expected else "behind_pace"


# ---------------------------------------------------------------------------
# Daily drift-snapshot log — a lightweight per-goal rolling history distinct
# from the manual metric's own user-logged history above; written once a day
# by the scheduler for EVERY goal regardless of metric type, purely so
# goal_drift can compare "percent N days ago" against "percent today".
# ---------------------------------------------------------------------------

_SNAPSHOT_CAP = 30  # ~1 month of daily snapshots is enough for any drift window


def snapshot_progress(store_user: str, workspace: str, user: dict) -> list[dict]:
    """Writes today's snapshot; returns the goals that crossed from <100%
    to >=100% since the most recent PRIOR snapshot (empty on the very first
    snapshot ever, since there's nothing to compare against yet) — this is
    what the completion-celebration notification fires off of. Detected
    once a day at this cadence rather than instantly on every write, since a
    metric-driven goal's percent can change from an entirely different
    module's own write (e.g. a Finance transaction posted elsewhere) with no
    Goals-specific write happening at all to hook a real-time check onto."""
    goals = list_goals(store_user, workspace)
    if not goals:
        return []
    today = datetime.now(ZoneInfo("UTC")).date().isoformat()
    snapshot = {g["id"]: compute_progress(store_user, g, workspace, user, goals)["pct"] for g in goals}

    hist = read_json(goal_progress_history_path(store_user, workspace), default={"entries": []})
    prior_entries = [e for e in (hist.get("entries") or []) if e.get("date") != today]
    prior = prior_entries[-1]["pct_by_goal"] if prior_entries else {}
    newly_complete = [
        g
        for g in goals
        if snapshot.get(g["id"], 0) >= 100 and prior.get(g["id"], 0) < 100
    ]

    def _update(hist: dict) -> dict:
        entries = list(hist.get("entries") or [])
        entries = [e for e in entries if e.get("date") != today]
        entries.append({"date": today, "pct_by_goal": snapshot})
        hist["entries"] = entries[-_SNAPSHOT_CAP:]
        return hist

    update_json(goal_progress_history_path(store_user, workspace), _update, default={"entries": []})
    return newly_complete


def progress_snapshot_days_ago(store_user: str, goal_id: str, days: int, workspace: str = "personal") -> int | None:
    """This goal's snapshotted percent from `days` ago, or None if no
    snapshot old enough exists yet (e.g. the goal was created recently)."""
    target_date = (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=days)).isoformat()
    hist = read_json(goal_progress_history_path(store_user, workspace), default={"entries": []})
    entries = sorted(hist.get("entries") or [], key=lambda e: e["date"])
    candidate = None
    for e in entries:
        if e["date"] <= target_date:
            candidate = e
        else:
            break
    if candidate is None:
        return None
    return candidate.get("pct_by_goal", {}).get(goal_id)


# ---------------------------------------------------------------------------
# Upgrade migration helper — converts a legacy type=="goal" Task into a real
# Goal record. Pure function (no I/O) so the manifest's own migration and
# any test can call it identically.
# ---------------------------------------------------------------------------


def goal_from_legacy_task(task: dict) -> dict:
    return {
        "id": task["id"],
        "title": task["title"],
        "notes": task.get("notes"),
        "category": task.get("category", ""),
        "parent_id": None,
        "due_date": task.get("due_date"),
        "status": task.get("status", "pending"),
        "metric": None,
        "tags": [],
        "created_by": task.get("created_by"),
        "created_at": task.get("created_at") or datetime.now(ZoneInfo("UTC")).isoformat(),
        "updated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
    }


def write_json_direct(store_user: str, workspace: str, data: dict) -> None:
    """Thin pass-through so the migration (which already holds its own lock
    semantics across tasks.json + goals.json together) can write without a
    second nested update_json lock acquisition."""
    write_json(goals_path(store_user, workspace), data)
