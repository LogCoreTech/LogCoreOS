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

ALL_MODULE_IDS = [
    "dashboard",
    "tasks",
    "goals",
    "calendar",
    "household",
    "notes",
    "journal",
    "chat",
    "automations",
    "automations_business",
    "home",
    "team",
    "assets",
]

_PERSONAL_MEMBER = {m: True for m in ALL_MODULE_IDS if m not in ("automations_business", "team")}

_BUSINESS_MEMBER = {
    "dashboard": True,
    "tasks": True,
    "goals": True,
    "calendar": True,
    "household": False,
    "notes": True,
    "journal": False,
    "chat": True,
    "automations": True,
    "automations_business": True,
    "home": False,
    "team": True,
    "assets": True,
}

_DEFAULT_FEATURES: dict = {
    "profile": "personal",
    "roles": {
        "member": _PERSONAL_MEMBER.copy(),
        "guest": _PERSONAL_MEMBER.copy(),
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
        roles["guest"] = _PERSONAL_MEMBER.copy()
    # Fill in any missing module keys for each role
    for role_name, role_map in roles.items():
        for mod in ALL_MODULE_IDS:
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
    save_features({"profile": profile, "roles": {"member": member_map, "guest": member_map.copy()}})


def get_effective_disabled(
    feature_role: str,
    user_disabled_modules,
    workspace: str = "personal",
) -> list[str]:
    """Compute the effective list of disabled module IDs for a user in the given workspace.

    user_disabled_modules can be:
      - list[str]: legacy flat list applied to every workspace
      - dict[str, list[str]]: workspace-keyed {"personal": [...], "business": [...]}
    """
    features = load_features()
    roles = features.get("roles", {})

    role_map = roles.get(feature_role) or roles.get("member") or {}
    role_disabled = {mod for mod, enabled in role_map.items() if not enabled}

    if isinstance(user_disabled_modules, dict):
        user_disabled = set(user_disabled_modules.get(workspace, []))
    else:
        user_disabled = set(user_disabled_modules or [])

    return sorted(role_disabled | user_disabled)
