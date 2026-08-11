"""Tests for the agent's Dashboard tools (2026-08-09) — access-tier gating,
templated-dashboard block-mutation rejection, the global-template admin gate,
the block catalog's merged config_fields, and the y:Infinity->null bug class
staying fixed on this server-side path too (see Dashboard.jsx's nextY())."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services import agent_service, auth_service, dashboard_templates_service, dashboards_service
from services.dashboard_blocks.registry import _load_all_resolvers

_load_all_resolvers()


@pytest.fixture()
def users(brain):
    alice = auth_service.create_user("alice@example.com", "password123", "Alice", role="admin")
    bob = auth_service.create_user("bob@example.com", "password123", "Bob")
    yield {"alice": alice, "bob": bob}
    auth_service._revoked_jtis.clear()


def test_add_dashboard_block_stacks_real_integer_not_null(users):
    """The exact bug class fixed in Dashboard.jsx's addBlock() (2026-08-09):
    a bottom-stacked default layout must be a real computed integer, never a
    sentinel that could serialize to null."""
    d = dashboards_service.create_dashboard("Alice", "personal", "Alice", "Board")

    r1 = agent_service._execute_tool(
        "add_dashboard_block",
        {"dashboard_id": d["id"], "type": "top3_tasks", "config": {}},
        users["alice"],
        workspace="personal",
    )
    assert r1["ok"] is True
    stored = dashboards_service.get_dashboard("Alice", d["id"], "personal")
    first_y = stored["blocks"][0]["layout"]["lg"]["y"]
    assert first_y == 0
    assert isinstance(first_y, int)

    r2 = agent_service._execute_tool(
        "add_dashboard_block",
        {"dashboard_id": d["id"], "type": "due_today", "config": {}},
        users["alice"],
        workspace="personal",
    )
    assert r2["ok"] is True
    stored2 = dashboards_service.get_dashboard("Alice", d["id"], "personal")
    second_y = stored2["blocks"][1]["layout"]["lg"]["y"]
    assert second_y is not None
    assert second_y == 9  # stacked directly below the first block's h=9


def test_add_dashboard_block_requires_contribute_or_edit_access(users):
    d = dashboards_service.create_dashboard("Alice", "personal", "Alice", "Board")
    dashboards_service.update_access(
        "Alice", "personal", d["id"], shared_with=[{"target": "Bob", "access": "read"}], by="Alice"
    )
    dashboards_service.respond_to_share("Bob", "Alice", "personal", d["id"], True)

    result = agent_service._execute_tool(
        "add_dashboard_block",
        {"dashboard_id": d["id"], "type": "top3_tasks", "config": {}},
        users["bob"],
        workspace="personal",
    )
    assert "error" in result
    stored = dashboards_service.get_dashboard("Alice", d["id"], "personal")
    assert stored["blocks"] == []


def test_dashboard_id_not_found_or_inaccessible(users):
    result = agent_service._execute_tool(
        "add_dashboard_block",
        {"dashboard_id": "does-not-exist", "type": "top3_tasks", "config": {}},
        users["bob"],
        workspace="personal",
    )
    assert "error" in result


@pytest.mark.parametrize(
    "tool_name,extra_inputs",
    [
        ("add_dashboard_block", {"type": "top3_tasks", "config": {}}),
        ("update_dashboard_block", {"block_id": "slot-1", "config": {}}),
        ("remove_dashboard_block", {"block_id": "slot-1"}),
    ],
)
def test_block_mutation_tools_reject_templated_dashboard(users, tool_name, extra_inputs):
    tmpl = dashboard_templates_service.create_template(
        {
            "label": "Client Overview",
            "blocks": [{"id": "slot-1", "type": "top3_tasks", "config": {}}],
        },
        owner=dashboard_templates_service.GLOBAL_OWNER,
    )
    d = dashboards_service.create_dashboard(
        "Alice", "personal", "Alice", "From Template", template_id=tmpl["id"]
    )

    result = agent_service._execute_tool(
        "add_dashboard_block" if tool_name == "add_dashboard_block" else tool_name,
        {"dashboard_id": d["id"], **extra_inputs},
        users["alice"],
        workspace="personal",
    )
    assert "error" in result
    assert "template" in result["error"].lower()
    # Untouched — still exactly the one template-derived slot.
    stored = dashboards_service.get_dashboard("Alice", d["id"], "personal")
    assert len(stored["blocks"]) == 1
    assert stored["blocks"][0]["id"] == "slot-1"


def test_create_dashboard_template_global_requires_admin(users):
    result = agent_service._execute_tool(
        "create_dashboard_template",
        {"label": "Instance Template", "owner": "global", "blocks": []},
        users["bob"],
        workspace="personal",
    )
    assert "error" in result
    assert "admin" in result["error"].lower()
    assert dashboard_templates_service.list_global_templates() == []


def test_create_dashboard_template_personal_allowed_for_any_user(users):
    result = agent_service._execute_tool(
        "create_dashboard_template",
        {"label": "My Own Template", "owner": "me", "blocks": []},
        users["bob"],
        workspace="personal",
    )
    assert "error" not in result
    assert result["label"] == "My Own Template"
    assert (
        dashboard_templates_service.list_personal_templates("Bob")[0]["label"] == "My Own Template"
    )


def test_update_dashboard_template_global_requires_admin(users):
    tmpl = dashboard_templates_service.create_template(
        {"label": "Instance Template", "blocks": []},
        owner=dashboard_templates_service.GLOBAL_OWNER,
    )
    result = agent_service._execute_tool(
        "update_dashboard_template",
        {"template_id": tmpl["id"], "label": "Hijacked"},
        users["bob"],
        workspace="personal",
    )
    assert "error" in result
    assert "admin" in result["error"].lower()
    assert (
        dashboard_templates_service.get_template_by_id(tmpl["id"])["label"] == "Instance Template"
    )


def test_update_dashboard_template_personal_owner_only(users):
    tmpl = dashboard_templates_service.create_template(
        {"label": "Bob's Template", "blocks": []}, owner="Bob"
    )
    result = agent_service._execute_tool(
        "update_dashboard_template",
        {"template_id": tmpl["id"], "label": "Stolen"},
        users["alice"],
        workspace="personal",
    )
    assert "error" in result
    assert dashboard_templates_service.get_template_by_id(tmpl["id"])["label"] == "Bob's Template"


def test_create_dashboard_pool_requires_admin(users):
    result = agent_service._execute_tool(
        "create_dashboard",
        {"name": "Household Board", "pool": True},
        users["bob"],
        workspace="personal",
    )
    assert "error" in result
    assert "admin" in result["error"].lower()


def test_get_dashboard_block_catalog_merges_config_fields(users):
    catalog = agent_service._execute_tool(
        "get_dashboard_block_catalog", {}, users["alice"], workspace="personal"
    )
    by_type = {c["type"]: c for c in catalog}
    assert "single_task" in by_type
    assert by_type["single_task"]["config_fields"] == [
        {"key": "task_id", "label": "Task id (look it up via list_tasks)", "kind": "task"}
    ]
    # A type with no config (e.g. top3_tasks) still appears, with an empty list.
    assert by_type["top3_tasks"]["config_fields"] == []
