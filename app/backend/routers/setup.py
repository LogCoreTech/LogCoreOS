"""Setup wizard — scaffolds the Brain folder for a new user after registration."""
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config import settings
from routers.auth import get_current_user
from services.file_service import brain_path, write_markdown, user_path

router = APIRouter()

TEMPLATE_PATH = brain_path() / "USERS" / "_template"


class SetupRequest(BaseModel):
    priority_order: list[str]
    custom_categories: list[str] = []
    role: str = ""
    timezone: str = "America/Chicago"


@router.post("")
def setup_user(req: SetupRequest, current_user: dict = Depends(get_current_user)):
    """Create Brain folder structure for a newly registered user."""
    name = current_user["name"]
    dest = user_path(name)

    if dest.exists():
        return {"ok": True, "message": "User folder already exists"}

    # Copy template
    shutil.copytree(str(TEMPLATE_PATH), str(dest))

    # Rename profile file
    template_profile = dest / "Profile.md"
    profile_content = template_profile.read_text()
    profile_content = profile_content.replace("{Full Name}", name)
    profile_content = profile_content.replace("{e.g., Electrician, Teacher, Student}", req.role)
    profile_content = profile_content.replace("{e.g., America/Chicago}", req.timezone)

    # Inject priority order
    all_categories = req.priority_order + req.custom_categories
    priority_lines = "\n".join(f"{i+1}. {cat}" for i, cat in enumerate(all_categories))
    custom_lines = "\n".join(f"- {cat}" for cat in req.custom_categories) or "- (none)"

    import re
    # Replace priority list block
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

    # Replace placeholders in memory files
    for md_file in [dest / "Long_Term_Memory.md", dest / "Short_Term_Memory.md"]:
        content = md_file.read_text().replace("{Full Name}", name)
        md_file.write_text(content)

    # Update USERS.md to register this user
    users_md = brain_path() / "USERS.md"
    users_content = users_md.read_text()
    if name not in users_content:
        users_content = users_content.replace(
            "| — | — | No users yet — run setup wizard |",
            f"| {name} | `USERS/{name}/` | Active |",
        )
        users_md.write_text(users_content)

    return {"ok": True, "message": f"Brain folder created for {name}"}
