from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from config import settings
from routers.auth import get_current_user, require_module
from services.auth_service import today_for_user
from services.file_service import (
    read_markdown,
    write_markdown,
    profile_path,
    tasks_path,
    read_json,
    user_path,
)
from services.ai_provider import chat_completion, is_ai_configured
from services.agent_service import run_agent
from services.rate_limiter import rate_limit

router = APIRouter()

_require_chat = require_module("chat")
_chat_limit   = rate_limit(20, 60)  # 20 messages per minute per IP
_memory_limit = rate_limit(5, 60)    # 5 memory saves per minute per IP
_save_limit   = rate_limit(30, 60)  # 30 chat auto-saves per minute per IP

_MEMORY_MAX_BYTES = 100_000  # 100 KB cap per memory file


def _safe(content: str) -> str:
    """Wrap user-controlled content in XML tags to prevent prompt injection.
    Escapes any closing tag sequences so they cannot break out of the envelope."""
    escaped = content.replace("</brain_data>", "[/brain_data]")
    return f"<brain_data>\n{escaped}\n</brain_data>"


def _build_context(user_name: str) -> str:
    """Assemble the user's Brain context for the AI system prompt."""
    parts = []

    pf = profile_path(user_name)
    if pf.exists():
        parts.append(f"# User Profile\n\n{_safe(read_markdown(pf))}")

    ltm = user_path(user_name) / "Long_Term_Memory.md"
    if ltm.exists():
        parts.append(f"# Long-Term Memory\n\n{_safe(read_markdown(ltm))}")

    stm = user_path(user_name) / "Short_Term_Memory.md"
    if stm.exists():
        parts.append(f"# Short-Term Memory\n\n{_safe(read_markdown(stm))}")

    tp = tasks_path(user_name)
    if tp.exists():
        tasks = read_json(tp).get("tasks", [])
        pending = [t for t in tasks if t.get("status") == "pending"]
        task_lines = "\n".join(
            f"- [{t['category']}] {t['title']} ({t['priority']})"
            + (f" — due {t['due_date']}" if t.get("due_date") else "")
            for t in pending
        )
        parts.append(f"# Pending Tasks\n\n{_safe(task_lines or '(none)')}")

    return "\n\n---\n\n".join(parts)


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=5000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    history: list[HistoryMessage] = Field(default=[], max_length=50)
    mode: Literal["plan", "auto", "research"] = "plan"

    @model_validator(mode="after")
    def validate_history_alternates(self):
        h = self.history
        if not h:
            return self
        if h[0].role != "user":
            raise ValueError("History must begin with a user message")
        for i, msg in enumerate(h):
            if msg.role != ("user" if i % 2 == 0 else "assistant"):
                raise ValueError(f"History message {i} has unexpected role '{msg.role}'")
        if h[-1].role != "assistant":
            raise ValueError("History must end with an assistant message")
        return self


@router.post("")
async def chat(
    req: ChatRequest,
    current_user: dict = Depends(_require_chat),
    _rl: None = Depends(_chat_limit),
):
    if not is_ai_configured():
        return {
            "response": "AI is not configured. Ask your admin to set up an AI provider in the Admin panel.",
            "steps": [],
            "mode": "error",
        }

    from datetime import datetime
    from zoneinfo import ZoneInfo
    user_tz = current_user.get("timezone", "UTC")
    try:
        now_local = datetime.now(ZoneInfo(user_tz))
    except Exception:
        now_local = datetime.now(ZoneInfo("UTC"))
    today_str = now_local.strftime("%A, %B %d, %Y (%Y-%m-%d)")

    mode_block = ""
    if req.mode == "plan":
        mode_block = (
            "IMPORTANT — before creating, updating, or deleting anything, always call propose_plan "
            "with a plain-English summary and list of specific actions. Do not call any other write "
            "tools in the same turn as propose_plan — wait for the user to confirm first. "
            "Read-only tools (list_tasks, get_profile, search_brain, etc.) do not need propose_plan.\n\n"
        )
    elif req.mode == "research":
        mode_block = (
            "You are in RESEARCH MODE. Your role is to gather, analyze, and synthesize information "
            "from the user's personal Brain data and the web. You have READ-ONLY access — do NOT "
            "propose or attempt any modifications. Use search_brain for personal data and search_web "
            "for external research. Deliver comprehensive, well-organized findings.\n\n"
        )

    tool_guidance = (
        "Tool guidance:\n"
        "- Goals the user wants to complete (lose weight, learn Spanish) → tasks with type='goal'\n"
        "- Calendar appointments/events → tasks with type='appointment', due_date, and optionally due_time\n"
        "- Notes → use list_notes, create_note, update_note, delete_note\n"
        "- Profile details (occupation, health, family, life mission, values, AI preferences) → get_profile then update_profile\n"
        "- Save something to memory → append_memory (short for recent context, long for stable facts)\n\n"
        "Planning guidance:\n"
        "- 'Plan my week' → call get_week_snapshot, reason about priorities and gaps, call propose_plan listing tasks to create, then create_tasks on confirmation\n"
        "- 'Break [goal] into tasks' → reason about 3–7 concrete subtasks, call propose_plan, then create_tasks on confirmation\n"
        "- 'Organize tasks by project/category' → call list_tasks, group by category and summarize — read-only, no propose_plan needed\n"
        "- 'Summarize my progress' → call get_task_history with since_date + list_journal_entries — read-only, no propose_plan needed\n\n"
    ) if req.mode != "research" else ""

    system_prompt = (
        f"You are the AI layer of LogCore Brain — a personal life operating system. "
        f"Today is {today_str}. "
        "You know this user personally from the context below. Be direct and concise. "
        "Help them manage their life priorities and tasks. "
        "When the user asks you to take an action, use the appropriate tool.\n\n"
        + mode_block
        + tool_guidance
        + _build_context(current_user["name"])
    )

    history = [m.model_dump() for m in req.history]
    result = await run_agent(current_user, req.message, history, system_prompt, mode=req.mode)

    return {
        "response": result["final_answer"],
        "steps": result["steps"],
        "mode": result["status"],
    }


class SaveMemoryRequest(BaseModel):
    history: list[HistoryMessage] = Field(..., min_length=1, max_length=50)
    target: Literal["short", "long"] = "short"


@router.post("/save-memory")
async def save_memory(
    req: SaveMemoryRequest,
    current_user: dict = Depends(_require_chat),
    _rl: None = Depends(_memory_limit),
):
    if not is_ai_configured():
        raise HTTPException(status_code=503, detail="AI not configured.")

    convo = "\n".join(f"{m.role.upper()}: {m.content}" for m in req.history)
    extract_prompt = (
        "Extract the key facts, decisions, and insights from this conversation that are worth "
        "remembering long-term. Be concise — bullet points only, max 5 bullets. "
        "Do NOT include pleasantries or questions. Only concrete information.\n\n"
        f"Conversation:\n{convo}"
    )
    summary = await chat_completion(
        "You are a memory extractor. Output only a markdown bullet list. No preamble.",
        [{"role": "user", "content": extract_prompt}],
    )

    fname = "Long_Term_Memory.md" if req.target == "long" else "Short_Term_Memory.md"
    mem_path = user_path(current_user["name"]) / fname
    today = today_for_user(current_user["name"]).isoformat()

    existing = mem_path.read_text() if mem_path.exists() else ""
    if len(existing.encode()) >= _MEMORY_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Memory file is full. Clear some entries before saving more.")

    # Escape any brain_data closing tags in AI output to prevent prompt injection via memory
    safe_summary = summary.strip().replace("</brain_data>", "[/brain_data]")
    updated = existing.rstrip() + f"\n\n## {today}\n\n{safe_summary}\n"
    write_markdown(mem_path, updated)

    return {"ok": True, "target": fname, "summary": safe_summary}


class ChatSaveRequest(BaseModel):
    history: list[HistoryMessage] = Field(..., min_length=1, max_length=50)
    name: str = Field("", max_length=100)
    filename: str = Field("", max_length=50)  # if set, overwrite this existing file


@router.post("/save")
async def save_chat(
    req: ChatSaveRequest,
    current_user: dict = Depends(_require_chat),
    _rl: None = Depends(_save_limit),
):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    user_tz = current_user.get("timezone", "UTC")
    try:
        now = datetime.now(ZoneInfo(user_tz))
    except Exception:
        now = datetime.now(ZoneInfo("UTC"))

    chats_dir = user_path(current_user["name"]) / "Chats"
    chats_dir.mkdir(parents=True, exist_ok=True)

    # Overwrite existing file if filename provided, otherwise create new
    if req.filename.strip():
        target = (chats_dir / req.filename.strip()).resolve()
        if not target.is_relative_to(chats_dir.resolve()):
            raise HTTPException(status_code=400, detail="Invalid filename")
        filename = req.filename.strip()
        # Preserve original title from first line if no new name given
        existing_title = None
        if target.exists():
            try:
                existing_title = target.open().readline().strip().lstrip('# ')
            except Exception:
                pass
        title = req.name.strip() or existing_title or "Chat"
    else:
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}.md"
        date_label = now.strftime("%B %d, %Y at %I:%M %p")
        title = req.name.strip() or f"Chat — {date_label}"

    date_label = now.strftime("%B %d, %Y at %I:%M %p")
    lines = [f"# {title}\n", f"*{date_label}*\n"]
    for msg in req.history:
        label = "**You**" if msg.role == "user" else "**AI**"
        lines.append(f"{label}: {msg.content}\n")

    write_markdown(chats_dir / filename, "\n".join(lines))
    return {"ok": True, "filename": filename, "title": title}


@router.get("/saved")
def list_saved_chats(current_user: dict = Depends(_require_chat)):
    chats_dir = user_path(current_user["name"]) / "Chats"
    if not chats_dir.exists():
        return []
    files = sorted(chats_dir.glob("*.md"), reverse=True)
    result = []
    for f in files:
        # Read only the first line to get the title cheaply
        try:
            first_line = f.open().readline().strip().lstrip('# ')
        except Exception:
            first_line = f.stem
        result.append({"filename": f.name, "path": f"Chats/{f.name}", "title": first_line})
    return result


@router.delete("/saved/{filename}")
def delete_saved_chat(filename: str, current_user: dict = Depends(_require_chat)):
    chats_dir = user_path(current_user["name"]) / "Chats"
    target = (chats_dir / filename).resolve()
    if not target.is_relative_to(chats_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Chat not found")
    target.unlink()
    return {"ok": True}


@router.get("/runs")
def list_runs(current_user: dict = Depends(get_current_user)):
    """Return recent agent runs for the current user (tool-using runs only)."""
    path = user_path(current_user["name"]) / "agent" / "runs.json"
    data = read_json(path, default={"runs": []})
    return data["runs"]


@router.get("/runs/{run_id}")
def get_run(run_id: str, current_user: dict = Depends(get_current_user)):
    path = user_path(current_user["name"]) / "agent" / "runs.json"
    data = read_json(path, default={"runs": []})
    for run in data["runs"]:
        if run["id"] == run_id:
            return run
    raise HTTPException(status_code=404, detail="Run not found")
