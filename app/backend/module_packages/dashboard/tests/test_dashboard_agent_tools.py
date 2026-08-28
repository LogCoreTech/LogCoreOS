"""Tests for the agent's Dashboard tools (2026-08-09) — access-tier gating,
templated-dashboard block-mutation rejection, the global-template admin gate,
the block catalog's merged config_fields, and the y:Infinity->null bug class
staying fixed on this server-side path too (see Dashboard.jsx's nextY()).

Moved from tests/test_agent_dashboard_tools.py when dashboard/ converted
(2026-08-27) — all 10 tools moved (unlike notes', no core-staying exception
tool exists here), so this file moved in full rather than being split.
Needs no explicit mark_installed call — dashboard is the third LOCKED
module, and conftest.py's own brain fixture already auto-installs every
discovered uninstallable=True module (a fix from Tasks' own conversion),
same as Chat's own moved tests needed zero explicit calls either."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

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


def test_add_dashboard_block_accepts_a_size_override(users):
    """2026-08-15: the agent can now request a size (owner ask — "resize the
    dashboard blocks that it edits"). Width only changes on lg (the 36-col
    desktop grid); sm stays full-width since mobile is one column; height
    changes on both so the block reads the same tall either way. Position is
    still always auto-stacked."""
    d = dashboards_service.create_dashboard("Alice", "personal", "Alice", "Board")

    r = agent_service._execute_tool(
        "add_dashboard_block",
        {
            "dashboard_id": d["id"],
            "type": "top3_tasks",
            "config": {},
            "layout": {"w": 18, "h": 15},
        },
        users["alice"],
        workspace="personal",
    )
    assert r["ok"] is True
    stored = dashboards_service.get_dashboard("Alice", d["id"], "personal")
    layout = stored["blocks"][0]["layout"]
    assert layout["lg"]["w"] == 18
    assert layout["lg"]["h"] == 15
    assert layout["sm"]["w"] == 12  # mobile stays full-width, untouched
    assert layout["sm"]["h"] == 15  # height still matches on mobile
    assert layout["lg"]["x"] == 0 and layout["lg"]["y"] == 0  # position unaffected


def test_add_dashboard_block_clamps_an_out_of_range_size(users):
    """A nonsense size (zero, negative, wider than the desktop grid itself)
    is clamped rather than stored as-is or rejected outright."""
    d = dashboards_service.create_dashboard("Alice", "personal", "Alice", "Board")

    r = agent_service._execute_tool(
        "add_dashboard_block",
        {
            "dashboard_id": d["id"],
            "type": "top3_tasks",
            "config": {},
            "layout": {"w": 999, "h": 0},
        },
        users["alice"],
        workspace="personal",
    )
    assert r["ok"] is True
    layout = dashboards_service.get_dashboard("Alice", d["id"], "personal")["blocks"][0]["layout"]
    assert layout["lg"]["w"] == 36  # clamped to the actual desktop grid width
    assert layout["lg"]["h"] == 1  # clamped to at least 1, never 0/negative


def test_update_dashboard_block_can_resize_without_moving(users):
    d = dashboards_service.create_dashboard("Alice", "personal", "Alice", "Board")
    agent_service._execute_tool(
        "add_dashboard_block",
        {"dashboard_id": d["id"], "type": "top3_tasks", "config": {}},
        users["alice"],
        workspace="personal",
    )
    agent_service._execute_tool(
        "add_dashboard_block",
        {"dashboard_id": d["id"], "type": "due_today", "config": {}},
        users["alice"],
        workspace="personal",
    )
    stored = dashboards_service.get_dashboard("Alice", d["id"], "personal")
    second_block_id = stored["blocks"][1]["id"]
    original_y = stored["blocks"][1]["layout"]["lg"]["y"]

    r = agent_service._execute_tool(
        "update_dashboard_block",
        {
            "dashboard_id": d["id"],
            "block_id": second_block_id,
            "config": {},
            "layout": {"w": 24},
        },
        users["alice"],
        workspace="personal",
    )
    assert r["ok"] is True
    updated = dashboards_service.get_dashboard("Alice", d["id"], "personal")
    updated_block = next(b for b in updated["blocks"] if b["id"] == second_block_id)
    assert updated_block["layout"]["lg"]["w"] == 24
    assert updated_block["layout"]["lg"]["y"] == original_y  # position untouched
    assert updated_block["layout"]["lg"]["h"] == 9  # h omitted from override -> unchanged


def test_update_dashboard_block_without_layout_leaves_size_untouched(users):
    d = dashboards_service.create_dashboard("Alice", "personal", "Alice", "Board")
    agent_service._execute_tool(
        "add_dashboard_block",
        {"dashboard_id": d["id"], "type": "top3_tasks", "config": {}, "layout": {"w": 20, "h": 11}},
        users["alice"],
        workspace="personal",
    )
    block_id = dashboards_service.get_dashboard("Alice", d["id"], "personal")["blocks"][0]["id"]

    r = agent_service._execute_tool(
        "update_dashboard_block",
        {"dashboard_id": d["id"], "block_id": block_id, "config": {"sort_mode": "date"}},
        users["alice"],
        workspace="personal",
    )
    assert r["ok"] is True
    updated = dashboards_service.get_dashboard("Alice", d["id"], "personal")["blocks"][0]
    assert updated["layout"]["lg"]["w"] == 20
    assert updated["layout"]["lg"]["h"] == 11
    assert updated["config"]["sort_mode"] == "date"


def test_get_dashboard_exposes_block_positions_and_grid_width(users):
    """2026-08-15: the agent can now read where blocks actually are (owner
    ask — "a coordinate system... to figure where blocks are positioned")."""
    d = dashboards_service.create_dashboard("Alice", "personal", "Alice", "Board")
    agent_service._execute_tool(
        "add_dashboard_block",
        {"dashboard_id": d["id"], "type": "top3_tasks", "config": {}, "layout": {"w": 18, "h": 10}},
        users["alice"],
        workspace="personal",
    )
    result = agent_service._execute_tool(
        "get_dashboard", {"dashboard_id": d["id"]}, users["alice"], workspace="personal"
    )
    assert result["grid"] == {"cols": 36, "row_px": 24}
    layout = result["blocks"][0]["layout"]
    assert layout == {"x": 0, "y": 0, "w": 18, "h": 10}


def test_update_dashboard_block_can_move_position(users):
    """The agent can now move (not just resize) an existing block."""
    d = dashboards_service.create_dashboard("Alice", "personal", "Alice", "Board")
    agent_service._execute_tool(
        "add_dashboard_block",
        {"dashboard_id": d["id"], "type": "top3_tasks", "config": {}},
        users["alice"],
        workspace="personal",
    )
    block_id = dashboards_service.get_dashboard("Alice", d["id"], "personal")["blocks"][0]["id"]

    r = agent_service._execute_tool(
        "update_dashboard_block",
        {
            "dashboard_id": d["id"],
            "block_id": block_id,
            "config": {},
            "layout": {"x": 12, "y": 5},
        },
        users["alice"],
        workspace="personal",
    )
    assert r["ok"] is True
    updated = dashboards_service.get_dashboard("Alice", d["id"], "personal")["blocks"][0]
    assert updated["layout"]["lg"]["x"] == 12
    assert updated["layout"]["lg"]["y"] == 5
    assert updated["layout"]["lg"]["w"] == 12  # untouched, no w in the override
    # sm's own x/y are untouched by an lg-only move.
    assert updated["layout"]["sm"]["x"] == 0


def test_update_dashboard_block_clamps_position_against_width(users):
    """x is clamped so a block can never be placed hanging off the right
    edge of the desktop grid, accounting for its (possibly also just
    overridden) width."""
    d = dashboards_service.create_dashboard("Alice", "personal", "Alice", "Board")
    agent_service._execute_tool(
        "add_dashboard_block",
        {"dashboard_id": d["id"], "type": "top3_tasks", "config": {}},
        users["alice"],
        workspace="personal",
    )
    block_id = dashboards_service.get_dashboard("Alice", d["id"], "personal")["blocks"][0]["id"]

    r = agent_service._execute_tool(
        "update_dashboard_block",
        {
            "dashboard_id": d["id"],
            "block_id": block_id,
            "config": {},
            "layout": {"x": 999, "w": 30},
        },
        users["alice"],
        workspace="personal",
    )
    assert r["ok"] is True
    updated = dashboards_service.get_dashboard("Alice", d["id"], "personal")["blocks"][0]
    assert updated["layout"]["lg"]["w"] == 30
    assert updated["layout"]["lg"]["x"] == 6  # clamped to 36 - 30, not left hanging off the edge


def test_add_dashboard_block_ignores_a_stray_position_in_layout(users):
    """add_dashboard_block's own schema has no x/y — even if a model sends
    them anyway, position must still come only from stacked_layout()."""
    d = dashboards_service.create_dashboard("Alice", "personal", "Alice", "Board")
    r = agent_service._execute_tool(
        "add_dashboard_block",
        {
            "dashboard_id": d["id"],
            "type": "top3_tasks",
            "config": {},
            "layout": {"x": 20, "y": 20, "w": 15},
        },
        users["alice"],
        workspace="personal",
    )
    assert r["ok"] is True
    layout = dashboards_service.get_dashboard("Alice", d["id"], "personal")["blocks"][0]["layout"]
    assert layout["lg"]["w"] == 15  # size override still applies
    assert layout["lg"]["x"] == 0 and layout["lg"]["y"] == 0  # position ignored, still auto-stacked


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


def test_create_dashboard_pool_in_business_workspace_uses_personal_store_path(users):
    """Regression test (2026-08-18): pool pseudo-users (`_household`/`_team`)
    always store at the "personal" ws_path base regardless of which
    workspace they're paired with (file_service.ws_path()'s own contract).
    This tool used to pass the ambient `workspace` straight through, so a
    `_team` pool dashboard created while chatting in the business workspace
    was written to a location no read path ever looks at (every read
    hardcodes "personal" for pool stores) and vanished immediately — a
    "dashboard not found" 404 for everyone, including its creator. Found
    while investigating an unrelated user-reported "dashboard not found"
    bug; never reachable from the UI (which never sends pool=True for
    dashboards), only via this agent tool."""
    result = agent_service._execute_tool(
        "create_dashboard",
        {"name": "Team Board", "pool": True},
        users["alice"],
        workspace="business",
    )
    assert "id" in result

    found = dashboards_service.find_dashboard(
        users["alice"]["name"], "admin", True, "business", result["id"]
    )
    assert found is not None
    assert found["store"] == "_team"
    assert found["store_workspace"] == "personal"

    items = dashboards_service.list_visible_dashboards(
        users["alice"]["name"], "admin", True, "business"
    )
    assert any(d["id"] == result["id"] for d in items)


_CHROME_FIELDS = [
    {"key": "show_card", "label": "Show card background", "kind": "boolean", "optional": True},
    {
        "key": "show_header",
        "label": "Show header (when not editing)",
        "kind": "boolean",
        "optional": True,
    },
]


def test_get_dashboard_block_catalog_merges_config_fields(users):
    catalog = agent_service._execute_tool(
        "get_dashboard_block_catalog", {}, users["alice"], workspace="personal"
    )
    by_type = {c["type"]: c for c in catalog}
    assert "single_task" in by_type
    # Every non-chromeless type's own config fields are followed by the two
    # universal chrome toggles (2026-08-18) — appended, not merged in place.
    assert by_type["single_task"]["config_fields"] == [
        {"key": "task_id", "label": "Task id (look it up via list_tasks)", "kind": "task"},
        *_CHROME_FIELDS,
    ]
    # A type with no config of its own (e.g. streaks) still appears, and is
    # no longer an empty list — it always has at least the two chrome
    # fields now, since every non-chromeless block has a card/header to
    # toggle regardless of what else is configurable about it.
    assert by_type["streaks"]["config_fields"] == _CHROME_FIELDS
    # top3_tasks/due_today gained an optional sort_mode selector (2026-08-15).
    assert by_type["top3_tasks"]["config_fields"] == [
        {
            "key": "sort_mode",
            "label": "Sort order",
            "kind": "select",
            "optional": True,
            "options": [
                {"value": "priority", "label": "Priority"},
                {"value": "date", "label": "Date/Time"},
                {"value": "alpha", "label": "A–Z"},
            ],
        },
        *_CHROME_FIELDS,
    ]
    # Chromeless types (nav_button/status_button) have no card/header at
    # all — they must NOT gain the two chrome fields.
    nav_fields = by_type["nav_button"]["config_fields"]
    assert not any(f["key"] in ("show_card", "show_header") for f in nav_fields)
