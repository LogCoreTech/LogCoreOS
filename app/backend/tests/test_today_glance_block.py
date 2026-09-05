"""Tests for services/dashboard_blocks/_today_glance.py — the "Today at a
Glance" dashboard block (item #30, 2026-09-04 UX Polish Batch)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.dashboard_blocks._today_glance import resolve_today_glance
from services.dashboard_blocks.registry import REGISTRY, BlockRenderCtx


def _ctx(viewer="Alice", config=None, workspace="personal", is_admin=False, owner="Alice"):
    return BlockRenderCtx(
        viewer=viewer,
        viewer_role="member",
        is_admin=is_admin,
        workspace=workspace,
        config=config or {},
        dashboard_owner=owner,
    )


def test_registered_with_dashboard_module_gate():
    assert "today_glance" in REGISTRY
    assert REGISTRY["today_glance"].module == "dashboard"


def test_no_tasks_due_today(brain):
    result = resolve_today_glance(_ctx())
    assert result.ok is True
    assert result.data == {"done": 0, "total": 0}


def test_counts_done_vs_total_due_today(brain):
    from services.auth_service import today_for_user
    from services.task_service import add_task, update_task

    today = today_for_user("Alice").isoformat()
    t1 = add_task("Alice", {"title": "Task 1", "due_date": today})
    add_task("Alice", {"title": "Task 2", "due_date": today})
    add_task("Alice", {"title": "Not due today"})  # no due_date — excluded
    update_task("Alice", t1["id"], {"status": "done"})

    result = resolve_today_glance(_ctx())

    assert result.ok is True
    assert result.data == {"done": 1, "total": 2}


def test_locked_when_viewer_is_not_the_scoped_target(brain):
    # scope="owner" only resolves when viewer IS the dashboard owner (scoped_target's
    # own contract, shared by every scope_configurable block) — a shared viewer
    # who isn't the owner gets locked out, same as ai_usage_me/recent_ai_actions.
    result = resolve_today_glance(_ctx(viewer="Bob", owner="Alice", config={"scope": "owner"}))
    assert result.ok is False
    assert result.locked_reason == "no_access"
