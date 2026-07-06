"""Setup wizard — scaffolds the Brain folder for a new user after registration."""

import re
import shutil
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from config import settings
from routers.auth import get_current_user
from services import auth_service
from services.features_service import init_features
from services.file_service import brain_path, user_path, write_markdown
from services.rate_limiter import rate_limit

router = APIRouter()

_setup_limit = rate_limit(10, 60)  # 10 setup checks per minute

TEMPLATE_PATH = brain_path() / "USERS" / "_template"

# Characters that are safe inside markdown fields (no newlines, no heading markers)
_SAFE_TEXT_RE = re.compile(r"^[^\r\n#`*_\[\]|<>]{1,100}$")


def _sanitize(value: str, field: str) -> str:
    """Reject input that would inject markdown structure."""
    clean = value.strip()
    if not _SAFE_TEXT_RE.match(clean):
        raise HTTPException(
            status_code=400,
            detail=f"'{field}' contains invalid characters. "
            "Newlines and markdown control characters are not allowed.",
        )
    return clean


class SetupRequest(BaseModel):
    priority_order: list[str] = Field(..., min_length=1, max_length=20)
    custom_categories: list[str] = Field(default=[], max_length=10)
    role: str = Field(default="", max_length=100)
    timezone: str = Field(default="America/Chicago", max_length=50)
    profile: Literal["personal", "business"] = "personal"

    @field_validator("priority_order", "custom_categories", mode="before")
    @classmethod
    def validate_categories(cls, v: list) -> list:
        return [str(item)[:50] for item in v]


@router.get("/status")
def setup_status(current_user: dict = Depends(get_current_user), _rl: None = Depends(_setup_limit)):
    """Returns whether the user's Brain folder has been created.

    show_profile_type is True only before the first user completes setup (i.e. before
    features.json exists). All subsequent users skip that question — their profile choice
    would be ignored anyway since init_features() is a no-op once the file exists.
    """
    features_chosen = (brain_path() / "_system" / "features.json").exists()
    return {
        "setup_complete": user_path(current_user["name"]).exists(),
        "show_profile_type": not features_chosen,
        "enabled_workspaces": auth_service.enabled_workspaces(),
    }


@router.post("")
def setup_user(req: SetupRequest, current_user: dict = Depends(get_current_user)):
    """Create Brain folder structure for a newly registered user."""
    name = current_user["name"]
    dest = user_path(name)

    if dest.exists():
        return {"ok": True, "message": "User folder already exists"}

    # Validate timezone is a real IANA zone before writing anything
    try:
        ZoneInfo(req.timezone)
    except (ZoneInfoNotFoundError, Exception):
        raise HTTPException(status_code=400, detail=f"Invalid timezone: '{req.timezone}'")

    # Sanitize free-text fields before writing to markdown
    safe_role = _sanitize(req.role, "role") if req.role else ""
    safe_timezone = _sanitize(req.timezone, "timezone")
    # Validate all categories (custom_categories is a subset of priority_order, so validating
    # priority_order is sufficient — do NOT concatenate them or custom cats get written twice)
    for c in req.priority_order:
        _sanitize(c, "category")

    # Copy template — handle race where two simultaneous requests arrive for the same user
    try:
        shutil.copytree(str(TEMPLATE_PATH), str(dest))
    except FileExistsError:
        return {"ok": True, "message": "User folder already exists"}

    # Build profile content
    template_profile = dest / "Profile.md"
    profile_content = template_profile.read_text()
    profile_content = profile_content.replace("{Full Name}", name)
    profile_content = profile_content.replace("{e.g., Electrician, Teacher, Student}", safe_role)
    profile_content = profile_content.replace("{e.g., America/Chicago}", safe_timezone)

    # Inject priority order — priority_order already includes custom cats; never concatenate again
    priority_lines = "\n".join(f"{i+1}. {cat}" for i, cat in enumerate(req.priority_order))
    custom_lines = (
        "\n".join(f"- {_sanitize(cat, 'category')}" for cat in req.custom_categories) or "- (none)"
    )

    profile_content = re.sub(
        r"(Base categories in order.*?:)\n((?:\d+\..*\n?)+)",
        f"\\1\n{priority_lines}\n",
        profile_content,
        flags=re.MULTILINE,
    )
    profile_content = re.sub(
        r"(Custom categories.*?:)\n((?:-.*\n?)+)",
        f"\\1\n{custom_lines}\n",
        profile_content,
        flags=re.MULTILINE,
    )

    write_markdown(dest / "Profile.md", profile_content)

    # Seed profile.json so the Profile page reads canonical data without parsing Profile.md
    profile_json: dict = {"priority_order": req.priority_order}
    if safe_role:
        profile_json["occupation"] = safe_role
    from services.file_service import write_json

    write_json(dest / "profile.json", profile_json)

    # Replace placeholders in memory files (atomic writes)
    for md_file in [dest / "Long_Term_Memory.md", dest / "Short_Term_Memory.md"]:
        content = md_file.read_text().replace("{Full Name}", name)
        write_markdown(md_file, content)

    # Save timezone to auth record so scheduler and scoring use user's local date
    auth_service.update_user(current_user["id"], {"timezone": safe_timezone})

    # Register user in USERS.md (atomic write)
    users_md = brain_path() / "USERS.md"
    users_content = users_md.read_text()
    if name not in users_content:
        users_content = users_content.replace(
            "| — | — | No users yet — run setup wizard |",
            f"| {name} | `USERS/{name}/` | Active |",
        )
        write_markdown(users_md, users_content)

    # Initialise feature flags with chosen profile (no-op if features.json already exists)
    init_features(req.profile)

    return {"ok": True, "message": f"Brain folder created for {name}"}
