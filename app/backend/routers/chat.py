from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config import settings
from routers.auth import get_current_user
from services.file_service import (
    read_markdown,
    profile_path,
    tasks_path,
    read_json,
    user_path,
)

router = APIRouter()


def _build_context(user_name: str) -> str:
    """Assemble the user's Brain context for the AI system prompt."""
    parts = []

    # Profile
    pf = profile_path(user_name)
    if pf.exists():
        parts.append(f"# User Profile\n\n{read_markdown(pf)}")

    # Personal Long Term Memory
    ltm = user_path(user_name) / "Long_Term_Memory.md"
    if ltm.exists():
        parts.append(f"# Long-Term Memory\n\n{read_markdown(ltm)}")

    # Personal Short Term Memory
    stm = user_path(user_name) / "Short_Term_Memory.md"
    if stm.exists():
        parts.append(f"# Short-Term Memory\n\n{read_markdown(stm)}")

    # Tasks (pending only, summary)
    tp = tasks_path(user_name)
    if tp.exists():
        tasks = read_json(tp).get("tasks", [])
        pending = [t for t in tasks if t.get("status") == "pending"]
        task_lines = "\n".join(
            f"- [{t['category']}] {t['title']} ({t['priority']})"
            + (f" — due {t['due_date']}" if t.get("due_date") else "")
            for t in pending
        )
        parts.append(f"# Pending Tasks\n\n{task_lines or '(none)'}")

    return "\n\n---\n\n".join(parts)


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@router.post("")
async def chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    if not settings.anthropic_api_key:
        return {"response": "No AI API key configured. Set ANTHROPIC_API_KEY in .env."}

    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    system_prompt = (
        "You are the AI layer of LogCore Brain — a personal life operating system. "
        "You know this user personally from the context below. Be direct and concise. "
        "Help them manage their life priorities and tasks.\n\n"
        + _build_context(current_user["name"])
    )

    messages = req.history + [{"role": "user", "content": req.message}]

    response = client.messages.create(
        model=settings.ai_model,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    return {"response": response.content[0].text}
