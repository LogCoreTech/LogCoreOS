from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config import settings
from routers.auth import get_current_user, require_module
from services.file_service import (
    read_markdown,
    profile_path,
    tasks_path,
    read_json,
    user_path,
)
from services.ai_provider import chat_completion
from services.rate_limiter import rate_limit

router = APIRouter()

_require_chat = require_module("chat")
_chat_limit = rate_limit(20, 60)  # 20 messages per minute per IP


def _safe(content: str) -> str:
    """Wrap user-controlled content in XML tags to prevent prompt injection."""
    return f"<brain_data>\n{content}\n</brain_data>"


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
    response = chat_completion(system_prompt, messages)
    return {"response": response}
