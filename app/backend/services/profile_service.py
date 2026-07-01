"""Profile storage — reads/writes profile.json and regenerates Profile.md."""
from __future__ import annotations

from pathlib import Path

from services.file_service import read_json, user_path, ws_path, write_json, write_markdown

DEFAULT_PRIORITY_ORDER = ["God", "Family", "Job", "Personal Growth", "Hobbies"]


def _json_path(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "profile.json"


def _md_path(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "Profile.md"


def load_profile(user_name: str, workspace: str = "personal") -> dict:
    json_path = _json_path(user_name, workspace)
    if json_path.exists():
        return read_json(json_path, default={})
    # Legacy fallback: seed priority_order from Profile.md (personal workspace only)
    default: dict = {}
    if workspace == "personal":
        try:
            from services.file_service import parse_priority_order
            order = parse_priority_order(user_name)
            if order:
                default["priority_order"] = order
        except Exception:
            pass
    return default


def save_profile(user_name: str, data: dict, workspace: str = "personal") -> dict:
    if not data.get("priority_order"):
        data["priority_order"] = list(DEFAULT_PRIORITY_ORDER)
    write_json(_json_path(user_name, workspace), data)
    write_markdown(_md_path(user_name, workspace), generate_profile_md(user_name, data))
    return data


def get_priority_order(user_name: str, workspace: str = "personal") -> list[str]:
    """Return priority order from profile.json, falling back to Profile.md then defaults."""
    json_path = _json_path(user_name, workspace)
    if json_path.exists():
        data = read_json(json_path, default={})
        order = data.get("priority_order")
        if order and isinstance(order, list):
            return order
    # Legacy fallback: parse ## Life Priorities from Profile.md (personal workspace only)
    if workspace == "personal":
        try:
            from services.file_service import parse_priority_order
            order = parse_priority_order(user_name)
            if order:
                return order
        except Exception:
            pass
    return list(DEFAULT_PRIORITY_ORDER)


def generate_profile_md(user_name: str, data: dict) -> str:
    lines = [f"# {user_name} — Profile", ""]

    basics = []
    if data.get("occupation"):
        basics.append(f"**Occupation:** {data['occupation']}")
    loc = ", ".join(x for x in [data.get("city"), data.get("state"), data.get("country")] if x)
    if loc:
        basics.append(f"**Location:** {loc}")
    if data.get("pronouns"):
        basics.append(f"**Pronouns:** {data['pronouns']}")
    lines.extend(basics)
    if basics:
        lines.append("")

    routine = [(lbl, data[k]) for k, lbl in [
        ("wake_weekday", "Wake (weekdays)"),
        ("wake_weekend", "Wake (weekends)"),
        ("bedtime", "Bedtime"),
        ("work_hours", "Work hours"),
    ] if data.get(k)]
    if routine:
        lines.append("## Daily Routine")
        lines.extend(f"- {lbl}: {v}" for lbl, v in routine)
        lines.append("")

    health = []
    hw = " · ".join(x for x in [data.get("height"), data.get("weight")] if x)
    if hw:
        health.append(("Height/Weight", hw))
    for k, lbl in [("blood_type", "Blood type"), ("diet", "Dietary restrictions"), ("exercise", "Exercise"), ("conditions", "Conditions"), ("medications", "Medications")]:
        if data.get(k):
            health.append((lbl, data[k]))
    if health:
        lines.append("## Health")
        lines.extend(f"- {lbl}: {v}" for lbl, v in health)
        lines.append("")

    work = [(lbl, data[k]) for k, lbl in [
        ("employer", "Employer"), ("industry", "Industry"), ("education", "Education"),
        ("years_experience", "Experience"), ("skills", "Key skills"),
    ] if data.get(k)]
    if work:
        lines.append("## Work & Career")
        lines.extend(f"- {lbl}: {v}" for lbl, v in work)
        lines.append("")

    family_lines = []
    if data.get("marital_status"):
        ms = data["marital_status"]
        if data.get("partner"):
            ms += f" ({data['partner']})"
        family_lines.append(f"- Marital status: {ms}")
    children = data.get("children", [])
    if children:
        cs = ", ".join(
            f"{c.get('name', '?')} ({c.get('age', '?')})"
            for c in children if isinstance(c, dict)
        )
        if cs:
            family_lines.append(f"- Children: {cs}")
    if data.get("pets"):
        family_lines.append(f"- Pets: {data['pets']}")
    if family_lines:
        lines.append("## Family")
        lines.extend(family_lines)
        lines.append("")

    finances = [(lbl, data[k]) for k, lbl in [
        ("income_range", "Income range"), ("savings_goal", "Savings goal"), ("budget_style", "Budget style"),
    ] if data.get(k)]
    if finances:
        lines.append("## Finances")
        lines.extend(f"- {lbl}: {v}" for lbl, v in finances)
        lines.append("")

    gv = [(lbl, data[k]) for k, lbl in [
        ("life_mission", "Life mission"), ("big_goal", "Big long-term goal"),
        ("core_values", "Core values"), ("key_constraints", "Key constraints"),
    ] if data.get(k)]
    if gv:
        lines.append("## Values & Principles")
        lines.extend(f"- {lbl}: {v}" for lbl, v in gv)
        lines.append("")

    priority_order = data.get("priority_order") or DEFAULT_PRIORITY_ORDER
    lines.append("## Life Priorities")
    lines.extend(f"{i}. {cat}" for i, cat in enumerate(priority_order, 1))
    lines.append("")

    ai = [(lbl, data[k]) for k, lbl in [
        ("communication_style", "Communication style"), ("tone", "Tone"),
        ("response_language", "Response language"), ("topics_to_emphasize", "Emphasize"),
        ("topics_to_avoid", "Avoid"),
    ] if data.get(k)]
    if ai:
        lines.append("## AI Preferences")
        lines.extend(f"- {lbl}: {v}" for lbl, v in ai)
        lines.append("")

    if data.get("notes"):
        lines.append("## Personal Notes")
        lines.append(data["notes"])
        lines.append("")

    return "\n".join(lines)
