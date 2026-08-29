"""Goals: hierarchy CRUD + progress + metric picker. Serves BOTH personal and
household/team pool goals from this one router (the same "a single owning
module serves personal + pool" shape Finance/Contacts/Assets/Notes already
use — not the older per-pool-router shape Tasks/Calendar predate that split
by), so pool-goal availability correctly ties to Goals' OWN install state
rather than needing Household/Team to import a sibling module's service.

Every non-list endpoint takes an explicit `pool: bool` (default False)
rather than trying to infer "which store does this id belong to" —
mirrors the existing precedent on POST /notes/file's own `pool: true` flag.
Reads require only require_module("goals"); pool WRITES additionally
require_pool_edit for that workspace's pool, exactly like household's/
team's own existing task/event endpoints.

IMPORTANT: a pool pseudo-user's OWN storage always lives at workspace=
"personal" regardless of which real workspace (personal/business) the
CALLING user is currently in — ws_path() only ever branches on "business"
for a REAL username (brain/USERS/{name}/Business/); _household/_team have
no such subfolder, their entire existence already encodes personal-vs-
business. Confirmed by direct read of team/backend/router.py, which calls
task_service.list_tasks(_TEAM) with no workspace arg anywhere (defaults to
"personal"). _store_for() below returns the real (store_user,
store_workspace) pair to use, not just a store_user."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from module_packages.goals.backend import service as goals_service
from routers.auth import get_workspace, require_module
from services.rate_limiter import rate_limit

_require_goals = require_module("goals")
_write_limit = rate_limit(30, 60)

router = APIRouter()


def _pool_user(workspace: str) -> str:
    return "_household" if workspace == "personal" else "_team"


def _pool_id(workspace: str) -> str:
    return "household" if workspace == "personal" else "team"


def _pool_installed(workspace: str) -> bool:
    from services import mod_store_service

    return mod_store_service.is_installed(_pool_id(workspace))


def _require_pool_write(workspace: str, current_user: dict) -> None:
    """Re-implements require_pool_edit's own check inline — that dependency
    factory is bound to a fixed pool string at router-build time, but here
    the pool depends on the request's own workspace, resolved at call time."""
    if current_user.get("role") == "admin":
        return
    if _pool_id(workspace) in (current_user.get("pool_edit") or []):
        return
    raise HTTPException(status_code=403, detail="You don't have permission to make changes here.")


def _store_for(pool: bool, workspace: str, current_user: dict) -> tuple[str, str]:
    """(store_user, store_workspace) — see module docstring for why pool
    goals always resolve to store_workspace="personal" regardless of the
    caller's own ambient workspace."""
    if pool:
        return _pool_user(workspace), "personal"
    return current_user["name"], workspace


def _validate_id(goal_id: str) -> str:
    try:
        UUID(goal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid goal ID format")
    return goal_id


class GoalCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    notes: str | None = Field(None, max_length=5000)
    category: str = Field("", max_length=50)
    parent_id: str | None = None
    due_date: str | None = None
    metric: dict | None = None
    tags: list[str] | None = None
    pool: bool = False


class GoalUpdate(BaseModel):
    title: str | None = Field(None, max_length=255)
    notes: str | None = Field(None, max_length=5000)
    category: str | None = Field(None, max_length=50)
    parent_id: str | None = None
    due_date: str | None = None
    status: Literal["pending", "done"] | None = None
    metric: dict | None = None
    tags: list[str] | None = None
    pool: bool = False


class MetricLog(BaseModel):
    value: float
    date: str | None = None
    pool: bool = False


def _annotate_with_progress(goals: list[dict], store_user: str, store_ws: str, owner_label: str) -> list[dict]:
    user = {"name": store_user}
    return [
        {**g, "_owner": owner_label, "progress": goals_service.compute_progress(store_user, g, store_ws, user, goals)}
        for g in goals
    ]


@router.get("")
def list_goals(
    current_user: dict = Depends(_require_goals),
    workspace: str = Depends(get_workspace),
):
    """Caller's own goals + the workspace's pool goals if that pool module
    is installed — matches every other pool-visible module's default (Tasks/
    Notes' visible-to-all-members shape, not Dashboards' contributors-gated
    one, per the owner's own confirmed choice for Goals)."""
    own = _annotate_with_progress(
        goals_service.list_goals(current_user["name"], workspace), current_user["name"], workspace, current_user["name"]
    )
    if not _pool_installed(workspace):
        return own
    pool_user = _pool_user(workspace)
    pool = _annotate_with_progress(goals_service.list_goals(pool_user, "personal"), pool_user, "personal", pool_user)
    return own + pool


@router.get("/metric-providers")
def list_metric_providers(current_user: dict = Depends(_require_goals)):
    """Every metric source currently available to configure on a goal — the
    built-in "manual" entry plus whatever module_registry.metric_providers()
    discovers from active modules. config_schema drives the frontend picker
    the same way blockRegistry.js's CONFIG_FIELD_SCHEMAS already does."""
    from module_registry import metric_providers

    providers = [
        {
            "key": "manual",
            "label": "Manual number entry",
            "config_schema": [
                {
                    "key": "direction",
                    "label": "Direction",
                    "kind": "select",
                    "options": [
                        {"value": "increase", "label": "Increase to target (e.g. pages read, savings)"},
                        {"value": "decrease", "label": "Decrease to target (e.g. weight, debt)"},
                    ],
                },
                {
                    "key": "start_value",
                    "label": "Starting value (required for \"decrease\")",
                    "kind": "number",
                    "optional": True,
                },
                {"key": "target_value", "label": "Target value", "kind": "number"},
            ],
        }
    ]
    for key, spec in metric_providers().items():
        providers.append({"key": key, "label": spec.label, "config_schema": spec.config_schema})
    return providers


@router.post("", status_code=201)
def create_goal(
    req: GoalCreate,
    current_user: dict = Depends(_require_goals),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    if req.pool:
        _require_pool_write(workspace, current_user)
    store_user, store_ws = _store_for(req.pool, workspace, current_user)
    payload = req.model_dump(exclude={"pool"})
    payload["created_by"] = current_user["name"]
    try:
        return goals_service.create_goal(store_user, payload, store_ws)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{goal_id}")
def get_goal(
    goal_id: str,
    pool: bool = False,
    current_user: dict = Depends(_require_goals),
    workspace: str = Depends(get_workspace),
):
    _validate_id(goal_id)
    if pool and not _pool_installed(workspace):
        raise HTTPException(status_code=404, detail="Goal not found")
    store_user, store_ws = _store_for(pool, workspace, current_user)
    goal = goals_service.get_goal(store_user, goal_id, store_ws)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    progress = goals_service.compute_progress(store_user, goal, store_ws, current_user)
    linked_tasks = goals_service.get_linked_tasks(store_user, goal_id, store_ws)
    for t in linked_tasks:
        if t.get("type") == "recurring":
            t["recurring_rate"] = round(goals_service.recurring_completion_rate(t))
    return {
        "goal": goal,
        "subgoals": goals_service.get_subgoals(store_user, goal_id, store_ws),
        "linked_tasks": linked_tasks,
        "progress": progress,
        "on_pace": goals_service.on_pace(goal, progress),
    }


@router.patch("/{goal_id}")
def update_goal(
    goal_id: str,
    req: GoalUpdate,
    current_user: dict = Depends(_require_goals),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_id(goal_id)
    if req.pool:
        _require_pool_write(workspace, current_user)
    store_user, store_ws = _store_for(req.pool, workspace, current_user)
    updates = req.model_dump(exclude_unset=True, exclude={"pool"})
    try:
        result = goals_service.update_goal(store_user, goal_id, updates, store_ws)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return result


@router.delete("/{goal_id}")
def delete_goal(
    goal_id: str,
    pool: bool = False,
    cascade: bool = False,
    delete_linked_tasks: bool = False,
    current_user: dict = Depends(_require_goals),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """Query params, not a request body — DELETE-with-body is awkward on the
    frontend (the shared lib/api.js `del()` helper doesn't pass one), and
    these three flags are simple enough booleans that query params are the
    more idiomatic REST shape anyway."""
    _validate_id(goal_id)
    if pool:
        _require_pool_write(workspace, current_user)
    store_user, store_ws = _store_for(pool, workspace, current_user)
    result = goals_service.delete_goal(
        store_user,
        goal_id,
        store_ws,
        cascade=cascade,
        delete_linked_tasks=delete_linked_tasks,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True, **result}


@router.post("/{goal_id}/metric/log")
def log_metric_value(
    goal_id: str,
    req: MetricLog,
    current_user: dict = Depends(_require_goals),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """Log a dated value for a manual-metric goal (weight, pages read, ...).
    Pool writes still require pool_edit even though logging a value isn't a
    structural edit — a value entered under someone else's judgement on a
    shared goal is exactly the kind of write that grant already governs."""
    _validate_id(goal_id)
    if req.pool:
        _require_pool_write(workspace, current_user)
    store_user, store_ws = _store_for(req.pool, workspace, current_user)
    result = goals_service.log_manual_value(store_user, goal_id, req.value, store_ws, req.date)
    if result is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return result
