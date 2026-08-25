"""
Feature flags and custom role management.

Stores in brain/_system/features.json:
  {
    "profile": "personal" | "business",
    "roles": {
      "member": { "dashboard": true, "tasks": true, ... },   # built-in, cannot be deleted
      "cleaner": { "dashboard": true, "tasks": true, "journal": false, ... },
      ...
    }
  }

Resolution order for a user's effective disabled modules:
  1. Look up user's feature_role (default: "member"); fall back to "member" if role missing
  2. Disabled = modules where role map says false
  3. Union with user's per-user disabled_modules (additive per-user overrides)
"""

import os
from pathlib import Path

from services.file_service import read_json, write_json

# Modules not yet converted into module_packages/ format — hardcoded here same
# as always. As each one converts, it's removed from this list and supplied
# dynamically by all_module_ids() instead, via its own manifest's install
# state. See module_registry.py.
_CORE_MODULE_IDS = [
    "dashboard",
    "tasks",
    "goals",
    "household",
    "notes",
    "chat",
    "team",
    "assets",
    "finance",
    "contacts",
]


def all_module_ids() -> list[str]:
    """Every valid module id right now: whatever's left of the hardcoded core
    list, unioned with every module_packages/ module currently installed.
    Call this fresh each time rather than caching — it must reflect live
    install state, not a snapshot from import time."""
    from module_registry import active_manifests

    return _CORE_MODULE_IDS + sorted(active_manifests())


_PERSONAL_MEMBER = {m: True for m in _CORE_MODULE_IDS if m != "team"}

_BUSINESS_MEMBER = {
    "dashboard": True,
    "tasks": True,
    "goals": True,
    "household": False,
    "notes": True,
    "chat": True,
    # "home_assistant" (id renamed from "home" 2026-08-24) stays explicit
    # here even though it's no longer in _CORE_MODULE_IDS (converted to
    # module_packages/home_assistant/, 2026-08-24) — this dict is
    # hand-authored, not derived, and load_features() defaults any module
    # MISSING from a role map to True. Without this explicit False, a fresh
    # business-profile instance would default Home Assistant to enabled,
    # which is wrong — it's personal-only.
    "home_assistant": False,
    "team": True,
    "assets": True,
    "finance": True,
    "contacts": True,
}


def _guest_map(base: dict) -> dict:
    """Guests never get finance or contacts by default — money and people/PII
    data are the most sensitive in the app, so they're opt-in per guest
    (m007/m008 apply this to existing installs)."""
    guest = base.copy()
    guest["finance"] = False
    guest["contacts"] = False
    return guest


_DEFAULT_FEATURES: dict = {
    "profile": "personal",
    "roles": {
        "member": _PERSONAL_MEMBER.copy(),
        "guest": _guest_map(_PERSONAL_MEMBER),
    },
}


def _features_path() -> Path:
    from config import settings

    return settings.brain_path / "_system" / "features.json"


def load_features() -> dict:
    """Load features.json; merge with defaults so missing keys are always present."""
    data = read_json(_features_path(), default={})
    result: dict = {**_DEFAULT_FEATURES, **data}
    # Ensure built-in roles always exist
    roles = dict(result.get("roles") or {})
    if "member" not in roles:
        roles["member"] = _PERSONAL_MEMBER.copy()
    if "guest" not in roles:
        roles["guest"] = _guest_map(_PERSONAL_MEMBER)
    # Fill in any missing module keys for each role
    for role_name, role_map in roles.items():
        for mod in all_module_ids():
            if mod not in role_map:
                role_map[mod] = True
    result["roles"] = roles
    return result


def save_features(data: dict) -> None:
    write_json(_features_path(), data)


def init_features(profile: str) -> None:
    """Called by setup wizard on first-user registration. No-op if features.json already exists."""
    path = _features_path()
    if path.exists():
        return
    member_map = _BUSINESS_MEMBER.copy() if profile == "business" else _PERSONAL_MEMBER.copy()
    save_features(
        {"profile": profile, "roles": {"member": member_map, "guest": _guest_map(member_map)}}
    )


def get_effective_disabled(
    feature_role: str,
    user_disabled_modules,
    workspace: str = "personal",
) -> list[str]:
    """Compute the effective list of disabled module IDs for a user in the given workspace.

    user_disabled_modules can be:
      - list[str]: legacy flat list applied to every workspace
      - dict[str, list[str]]: workspace-keyed {"personal": [...], "business": [...]}

    Also unions in every module_packages/ module that's discovered on disk but
    NOT currently installed — this is the single choke point that makes an
    "uninstalled" module's data actually inaccessible (Brain browser, AI
    tools, dashboard blocks all read disabled_modules through this
    function), rather than every consumer needing its own install-state
    check. Locked (uninstallable) modules are always installed by
    construction, so they never appear here.
    """
    features = load_features()
    roles = features.get("roles", {})

    role_map = roles.get(feature_role) or roles.get("member") or {}
    role_disabled = {mod for mod, enabled in role_map.items() if not enabled}

    if isinstance(user_disabled_modules, dict):
        user_disabled = set(user_disabled_modules.get(workspace, []))
    else:
        user_disabled = set(user_disabled_modules or [])

    from module_registry import discover_manifests
    from services import mod_store_service

    manifests, _errors = discover_manifests()
    not_installed = set(manifests) - mod_store_service.get_installed_ids()

    return sorted(role_disabled | user_disabled | not_installed)
