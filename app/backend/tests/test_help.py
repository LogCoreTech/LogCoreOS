"""Tests for the Help system: content service, AI capability index, get_help tool
gating, and onboarding state."""

import services.agent_service as agent_service
import services.help_service as help_service


def test_content_has_expected_shape():
    c = help_service.get_content()
    assert isinstance(c.get("sections"), list) and c["sections"]
    assert "faq" in c and "support" in c and "whats_new" in c
    ids = {s["id"] for s in c["sections"]}
    assert {"tasks", "finance", "chat", "getting-started"} <= ids
    # every section has the fields the UI + AI render
    for s in c["sections"]:
        assert s.get("id") and s.get("title") and s.get("blurb")


def test_as_text_full_includes_faq_and_anchors():
    full = help_service.as_text()
    assert full
    assert "Frequently Asked Questions" in full
    assert "/help#tasks" in full


def test_as_text_section_narrows():
    fin = help_service.as_text("finance")
    assert "Finance" in fin
    assert "/help#finance" in fin
    # a narrowed render doesn't drag in unrelated sections
    assert "/help#tasks" not in fin
    # unknown section id renders empty
    assert help_service.as_text("does-not-exist") == ""


def test_capabilities_index_respects_enabled_modules():
    idx = help_service.capabilities_index({"tasks"})
    assert "/help#tasks" in idx  # enabled module included
    assert "/help#finance" not in idx  # disabled module excluded
    assert "/help#getting-started" in idx  # module-less topics always included
    assert "/help#admin" not in idx  # admin_only never surfaced to the agent


def test_capabilities_index_all_when_unfiltered():
    idx = help_service.capabilities_index(None)
    assert "/help#finance" in idx and "/help#tasks" in idx


def test_get_help_tool_is_registered_and_read_gated():
    names = {t["name"] for t in agent_service._USER_TOOLS}
    assert "get_help" in names
    # read-only → runs freely in approve mode, and available in research mode
    assert "get_help" in agent_service._READ_TOOLS
    assert "get_help" in agent_service._RESEARCH_TOOLS


def test_onboarding_round_trip(brain):
    user = "Alice"
    assert help_service.get_onboarding(user) == {"dismissed": False, "done": []}

    help_service.set_onboarding(user, done=["priorities"])
    help_service.set_onboarding(user, done=["priorities", "first-task"])
    state = help_service.get_onboarding(user)
    # union + de-duplicated
    assert sorted(state["done"]) == ["first-task", "priorities"]
    assert state["dismissed"] is False

    help_service.set_onboarding(user, dismissed=True)
    assert help_service.get_onboarding(user)["dismissed"] is True
    # dismissing doesn't wipe recorded steps
    assert "priorities" in help_service.get_onboarding(user)["done"]
