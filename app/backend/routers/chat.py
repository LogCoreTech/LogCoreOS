import asyncio
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
from services.ai_provider import chat_completion
from services.rate_limiter import rate_limit

router = APIRouter()

_require_chat = require_module("chat")
_chat_limit   = rate_limit(20, 60)  # 20 messages per minute per IP
_memory_limit = rate_limit(5, 60)   # 5 memory saves per minute per IP

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
    if not settings.anthropic_api_key:
        return {"response": "No AI API key configured. Set ANTHROPIC_API_KEY in .env."}

    system_prompt = (
        "You are the AI layer of LogCore Brain — a personal life operating system. "
        "You know this user personally from the context below. Be direct and concise. "
        "Help them manage their life priorities and tasks.\n\n"
        + _build_context(current_user["name"])
    )

    messages = [m.model_dump() for m in req.history] + [{"role": "user", "content": req.message}]
    response = await asyncio.to_thread(chat_completion, system_prompt, messages)
    return {"response": response}


class SaveMemoryRequest(BaseModel):
    history: list[HistoryMessage] = Field(..., min_length=1, max_length=50)
    target: Literal["short", "long"] = "short"


@router.post("/save-memory")
async def save_memory(
    req: SaveMemoryRequest,
    current_user: dict = Depends(_require_chat),
    _rl: None = Depends(_memory_limit),
):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="No AI API key configured.")

    convo = "\n".join(f"{m.role.upper()}: {m.content}" for m in req.history)
    extract_prompt = (
        "Extract the key facts, decisions, and insights from this conversation that are worth "
        "remembering long-term. Be concise — bullet points only, max 5 bullets. "
        "Do NOT include pleasantries or questions. Only concrete information.\n\n"
        f"Conversation:\n{convo}"
    )
    summary = await asyncio.to_thread(
        chat_completion,
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
