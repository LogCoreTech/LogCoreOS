"""First-user setup decides the instance's enabled workspaces.

The setup router writes `enabled_workspaces: [profile]` on first-user setup only
(gated on features.json not existing yet). These tests cover the auth_service
mechanism it relies on and the gate condition itself.
"""

from services import auth_service
from services.features_service import init_features


def test_enabled_workspaces_defaults_to_both(brain):
    assert auth_service.enabled_workspaces() == ["personal", "business"]


def test_first_user_profile_disables_other_workspace(brain):
    # Mirrors routers/setup.py: first user picked "personal"
    auth_service.update_system_settings({"enabled_workspaces": ["personal"]})
    assert auth_service.enabled_workspaces() == ["personal"]

    # Admin re-enabling later restores both
    auth_service.update_system_settings({"enabled_workspaces": ["personal", "business"]})
    assert auth_service.enabled_workspaces() == ["personal", "business"]


def test_business_profile_keeps_only_business(brain):
    auth_service.update_system_settings({"enabled_workspaces": ["business"]})
    assert auth_service.enabled_workspaces() == ["business"]


def test_malformed_setting_never_locks_out(brain):
    auth_service.update_system_settings({"enabled_workspaces": []})
    assert auth_service.enabled_workspaces() == ["personal", "business"]
    auth_service.update_system_settings({"enabled_workspaces": ["bogus"]})
    assert auth_service.enabled_workspaces() == ["personal", "business"]


def test_first_user_gate_is_features_json(brain):
    # Before any setup: features.json absent → the router treats it as first-user
    assert not (brain / "_system" / "features.json").exists()
    init_features("personal")
    # After init: gate closed — subsequent setups must not rewrite enabled_workspaces
    assert (brain / "_system" / "features.json").exists()
