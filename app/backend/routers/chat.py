from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from config import settings
from routers.auth import get_current_user, get_workspace, require_module
from services import agent_service, ai_usage_service
from services.agent_service import run_agent
from services.ai_provider import chat_completion, is_ai_configured
from services.auth_service import today_for_user
from services.file_service import (
    read_json,
    read_markdown,
    tasks_path,
    user_path,
    write_markdown,
    ws_path,
)
from services.rate_limiter import rate_limit

router = APIRouter()

_require_chat = require_module("chat")
_chat_limit = rate_limit(20, 60)  # 20 messages per minute per IP
_memory_limit = rate_limit(5, 60)  # 5 memory saves per minute per IP
_save_limit = rate_limit(30, 60)  # 30 chat auto-saves per minute per IP
_presence_limit = rate_limit(10, 60)  # Chat.jsx pings every ~20s while visible

_MEMORY_MAX_BYTES = 100_000  # 100 KB cap per memory file


def _safe(content: str) -> str:
    """Wrap user-controlled content in XML tags to prevent prompt injection.
    Escapes any closing tag sequences so they cannot break out of the envelope."""
    escaped = content.replace("</brain_data>", "[/brain_data]")
    return f"<brain_data>\n{escaped}\n</brain_data>"


def _build_context(user_name: str, workspace: str = "personal") -> str:
    """Assemble the user's Brain context for the AI system prompt.

    The Profile is the user's self-contact (one record shared across both
    workspaces) — this is workspace-agnostic by construction, unlike the old
    Profile.md which was personal-only regardless of the active workspace.
    Memory and tasks are scoped to the active workspace.
    """
    from services import contacts_service, profile_service

    parts = []
    base = ws_path(user_name, workspace)

    self_contact = contacts_service.get_self_contact(user_name, create_if_missing=True)
    if self_contact:
        parts.append(
            f"# User Profile\n\n{_safe(contacts_service.format_profile_text(self_contact))}"
        )

    # Life priorities for the ACTIVE workspace (personal profile order in personal;
    # business profile order in business) plus the relevant shared-pool order. The
    # agent must weigh these before creating tasks or goals.
    try:
        own_order = profile_service.get_priority_order(user_name, workspace)
        pool_user = "_team" if workspace == "business" else "_household"
        pool_label = "Team" if workspace == "business" else "Household"
        pool_order = profile_service.get_priority_order(pool_user)
        prio_lines = f"Your {workspace} priorities (highest first): {', '.join(own_order)}"
        if pool_order:
            prio_lines += f"\n{pool_label} pool priorities: {', '.join(pool_order)}"
        parts.append(f"# Life Priorities\n\n{_safe(prio_lines)}")
    except Exception:
        pass

    ltm = base / "Long_Term_Memory.md"
    if ltm.exists():
        parts.append(f"# Long-Term Memory\n\n{_safe(read_markdown(ltm))}")

    stm = base / "Short_Term_Memory.md"
    if stm.exists():
        parts.append(f"# Short-Term Memory\n\n{_safe(read_markdown(stm))}")

    tp = tasks_path(user_name, workspace)
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


def _write_chat_archive(
    user_name: str, workspace: str, filename: str, title: str, history: list[dict]
) -> None:
    """Write (or overwrite) one chat archive file — the same markdown shape
    POST /chat/save has always produced, now also called directly by the main
    chat handler after every turn so a conversation is durably saved server-
    side without depending on the frontend's own debounced auto-save timer
    (which never fires if the user navigates away before it does)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("UTC"))
    date_label = now.strftime("%B %d, %Y at %I:%M %p")
    lines = [f"# {title}\n", f"*{date_label}*\n"]
    for msg in history:
        label = "**You**" if msg["role"] == "user" else "**AI**"
        lines.append(f"{label}: {msg['content']}\n")
    chats_dir = ws_path(user_name, workspace) / "Chats"
    chats_dir.mkdir(parents=True, exist_ok=True)
    write_markdown(chats_dir / filename, "\n".join(lines))


class HistoryMessage(BaseModel):
    # 30k cap: agent/research responses regularly exceed 5k chars; a lower cap here
    # makes auto-save 422 silently and blocks continuing chats that contain them.
    # User input stays capped at 5000 via ChatRequest.message.
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=30_000)


class ResumeAction(BaseModel):
    run_id: str = Field(..., max_length=64)
    decision: Literal["approve", "decline"] | None = None
    answer: list[str] | None = Field(default=None, max_length=10)


class ChatRequest(BaseModel):
    # Empty when resuming a paused turn — see validate_message_or_resume below.
    message: str = Field("", max_length=5000)
    history: list[HistoryMessage] = Field(default=[], max_length=50)
    # "approve" is the default: reads run freely, each write pauses for user approval
    mode: Literal["approve", "plan", "auto", "research"] = "approve"
    cross_workspace: bool = False
    # Set true to proceed past a soft AI-usage-cap confirmation (see ai_usage_service).
    accept_overage: bool = False
    resume: ResumeAction | None = None
    # Stable per-conversation id, minted client-side (crypto.randomUUID()) the
    # moment a genuinely new conversation starts — threads every turn of that
    # conversation to the same chat_sessions.json entry regardless of how many
    # separate POST /chat round trips it takes. Required: every real send from
    # Chat.jsx always has one by the time it can send at all.
    chat_id: str = Field(..., max_length=64)

    @model_validator(mode="after")
    def validate_message_or_resume(self):
        if not self.message.strip() and not self.resume:
            raise ValueError("Either message or resume must be provided")
        return self

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
        # A resume's history is correctly expected to end in the *user*
        # message whose reply is still pending (that's what's being
        # completed) — only a normal send's history must end in a finished
        # assistant turn. Chat.jsx's toResumeHistory()/toApiHistory() send
        # the right shape for each case; this just stops the resume shape
        # from being rejected as if it were the send shape (found 2026-08-15
        # — see docs/MEMORY.md for the full story, including the frontend
        # half of this fix).
        if not self.resume and h[-1].role != "assistant":
            raise ValueError("History must end with an assistant message")
        return self


@router.post("")
async def chat(
    req: ChatRequest,
    current_user: dict = Depends(_require_chat),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_chat_limit),
):
    if not is_ai_configured():
        return {
            "response": "AI is not configured. Ask your admin to set up an AI provider in the Admin panel.",
            "steps": [],
            "mode": "error",
        }

    usage = ai_usage_service.check_usage(current_user["name"])
    if usage["status"] == "blocked":
        return {
            "response": "You've reached your AI usage limit for this period. Contact your admin to raise it.",
            "steps": [],
            "mode": "usage_blocked",
        }
    if usage["status"] == "soft_confirm" and not req.accept_overage:
        return {
            "response": "You've reached your AI usage limit for this period. Continue anyway? "
            "Extra usage may cost more.",
            "steps": [],
            "mode": "usage_confirm_required",
        }
    if usage["status"] == "soft_confirm" and req.accept_overage:
        ai_usage_service.accept_overage(current_user["name"])

    resume_payload = None
    effective_mode = req.mode
    if req.resume:
        pending = agent_service.load_pending_turn(current_user["name"], req.resume.run_id)
        if not pending:
            return {
                "response": "That request is no longer available to approve — please ask again.",
                "steps": [],
                "mode": "expired",
            }
        # Consume it now so a double-submit (e.g. a repeated click) can't replay
        # the same write twice.
        agent_service.delete_pending_turn(current_user["name"], req.resume.run_id)
        effective_mode = pending["mode"]
        resume_payload = {**pending, "decision": req.resume.decision, "answer": req.resume.answer}

    # A resume continues whatever workspace the original paused turn was in —
    # same reasoning as run_agent's own workspace= argument below — never the
    # ambient header, which is just wherever the caller happens to be now.
    effective_workspace = resume_payload["workspace"] if resume_payload else workspace

    # Flip the session to "running" before the (potentially slow) agent call
    # below, not after — this is the only way the sidebar can show a live
    # "active" indicator for a conversation, including from a different tab
    # or after switching away to a different chat in this same one. Resolve
    # the archive filename/title now too (reused unchanged after the agent
    # call finishes) rather than duplicating this lookup twice.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    history = [m.model_dump() for m in req.history]
    existing_session = agent_service.get_session(
        current_user["name"], effective_workspace, req.chat_id
    )
    if existing_session:
        filename, title = existing_session["filename"], existing_session["title"]
    else:
        user_tz = current_user.get("timezone", "UTC")
        try:
            ts_local = datetime.now(ZoneInfo(user_tz))
        except Exception:
            ts_local = datetime.now(ZoneInfo("UTC"))
        filename = f"{ts_local.strftime('%Y-%m-%d_%H-%M-%S')}.md"
        first_user_content = next(
            (m["content"] for m in history if m["role"] == "user"), req.message
        )
        title = first_user_content[:60] + ("…" if len(first_user_content) > 60 else "")
    agent_service.upsert_session(
        current_user["name"],
        effective_workspace,
        req.chat_id,
        filename=filename,
        title=title,
        status="running",
    )

    # Save the user's own message right away, before the (potentially slow,
    # occasionally failing) agent call below — not bundled into the single
    # end-of-turn write further down (owner report, 2026-08-17: a message
    # could take 5-10s to "go through," and if the agent call errored or the
    # connection dropped before that write, the message vanished entirely —
    # nothing was ever saved for that turn, not even what the user typed). A
    # resume has nothing new to save here: the user's message that triggered
    # it was already durably saved this same way during the original
    # (paused) turn.
    if not resume_payload:
        _write_chat_archive(
            current_user["name"],
            effective_workspace,
            filename,
            title,
            history + [{"role": "user", "content": req.message}],
        )

    user_tz = current_user.get("timezone", "UTC")
    try:
        now_local = datetime.now(ZoneInfo(user_tz))
    except Exception:
        now_local = datetime.now(ZoneInfo("UTC"))
    today_str = now_local.strftime("%A, %B %d, %Y (%Y-%m-%d)")

    mode_block = ""
    if effective_mode == "approve":
        mode_block = (
            "Any change you attempt (create/update/delete) is paused and shown to the user "
            "for approval before it is applied — call tools normally and keep any lead-in text "
            "short. If the user declines, do not retry the change; ask what they want instead.\n\n"
        )
    elif effective_mode == "plan":
        mode_block = (
            "IMPORTANT — before creating, updating, or deleting anything, always call propose_plan "
            "with a plain-English summary and list of specific actions. Do not call any other write "
            "tools in the same turn as propose_plan — wait for the user to confirm first. "
            "Read-only tools (list_tasks, get_profile, search_brain, etc.) do not need propose_plan.\n\n"
        )
    elif effective_mode == "research":
        mode_block = (
            "You are in RESEARCH MODE. Your role is to gather, analyze, and synthesize information "
            "from the user's personal Brain data and the web. You have READ-ONLY access — do NOT "
            "propose or attempt any modifications. Use search_brain for personal data and search_web "
            "for external research. Deliver comprehensive, well-organized findings.\n\n"
        )

    tool_guidance = (
        (
            "Tool guidance:\n"
            "- BEFORE creating any task or goal, consult the Life Priorities list above for the "
            "active context (the user's own priorities; use the Household/Team pool priorities when "
            "the item belongs to that shared pool). Align the task's category with those priorities.\n"
            "- Goals the user wants to complete (lose weight, learn Spanish) → tasks with type='goal'. "
            "A goal MUST have a target date (due_date). If the user hasn't given one, ask for it "
            "before creating the goal — never invent a date.\n"
            "- Calendar appointments/events → tasks with type='appointment', due_date, and optionally due_time\n"
            "- Notes → use list_notes, create_note, update_note, delete_note\n"
            "- Profile details (occupation, health, family, life mission, values, AI preferences) → get_profile then update_profile\n"
            "- Save something to memory → append_memory (short for recent context, long for stable facts)\n\n"
            "Planning guidance:\n"
            "- 'Plan my week' → call get_week_snapshot, reason about priorities and gaps, call propose_plan listing tasks to create, then create_tasks on confirmation\n"
            "- 'Break [goal] into tasks' → reason about 3–7 concrete subtasks, call propose_plan, then create_tasks on confirmation\n"
            "- 'Organize tasks by project/category' → call list_tasks, group by category and summarize — read-only, no propose_plan needed\n"
            "- 'Summarize my progress' → call get_task_history with since_date + list_journal_entries — read-only, no propose_plan needed\n\n"
        )
        if effective_mode != "research"
        else ""
    )

    # Help awareness — works in every mode (including research): the AI knows what
    # LogCore can do, points the user to the right module, and reads the Help guide
    # (get_help) when they're confused or ask how to do something.
    from services import help_service
    from services.features_service import all_module_ids

    disabled = set(current_user.get("disabled_modules", []))
    enabled = {m for m in all_module_ids() if m not in disabled}
    cap_index = help_service.capabilities_index(enabled)
    help_guidance = (
        "Helping the user use LogCore:\n"
        "- If they ask how to do something, seem confused, or ask what LogCore can do, call "
        "get_help (optionally with a section id like 'finance' or 'sharing') and answer from it, "
        "citing the /help#<section> anchor so they can read more.\n"
        "- When a request fits a module, point them to it by name.\n"
        + (cap_index + "\n" if cap_index else "")
        + "\n"
    )

    system_prompt = (
        f"You are the AI layer of LogCore Brain — a personal life operating system. "
        f"Today is {today_str}. "
        "You know this user personally from the context below. Be direct and concise. "
        "Help them manage their life priorities and tasks. "
        "When the user asks you to take an action, use the appropriate tool.\n\n"
        + mode_block
        + tool_guidance
        + help_guidance
        + _build_context(current_user["name"], workspace)
    )

    try:
        result = await run_agent(
            current_user,
            req.message,
            history,
            system_prompt,
            mode=effective_mode,
            workspace=effective_workspace,
            cross_workspace=(
                resume_payload["cross_workspace"] if resume_payload else req.cross_workspace
            ),
            resume=resume_payload,
            chat_id=req.chat_id,
        )
    except Exception:
        # Don't leave the session stuck showing "running" forever if the agent
        # loop itself raises (e.g. a provider error) — same failure mode this
        # request always had; only new here is the status needing a reset.
        agent_service.upsert_session(
            current_user["name"], effective_workspace, req.chat_id, status="idle"
        )
        raise
    ai_usage_service.record_message(current_user["name"], workspace)

    # Persist + index server-side, unconditionally — not contingent on the
    # frontend still being mounted when this returns. Nothing here cancels
    # the request if the client navigates away mid-flight (no AbortController
    # is ever wired up client-side, and Starlette doesn't auto-cancel a
    # handler on client disconnect), so the turn was always going to finish;
    # the gap this closes is that the result previously had nowhere to land
    # once nobody was there to receive the HTTP response.
    if resume_payload:
        new_entries = [{"role": "assistant", "content": result["final_answer"]}]
    else:
        new_entries = [
            {"role": "user", "content": req.message},
            {"role": "assistant", "content": result["final_answer"]},
        ]
    full_history = history + new_entries
    _write_chat_archive(current_user["name"], effective_workspace, filename, title, full_history)

    session_status = (
        result["status"] if result["status"] in ("awaiting_approval", "awaiting_answer") else "idle"
    )
    # If the requesting user is still actively looking at this exact
    # conversation (Chat.jsx pings presence on mount/switch and on an
    # interval while visible — see agent_service.is_chat_present), it isn't
    # "unread" and doesn't need a notification either — owner ask,
    # 2026-08-15: "ai chat only needs to send a notification... when the
    # user is not on that module." They're watching it complete live either
    # way; nothing is lost by not also badging/pushing/inboxing it.
    user_present = agent_service.is_chat_present(current_user["name"], req.chat_id)
    agent_service.upsert_session(
        current_user["name"],
        effective_workspace,
        req.chat_id,
        filename=filename,
        title=title,
        status=session_status,
        updated_at=datetime.now(ZoneInfo("UTC")).isoformat(),
        last_message_preview=(result["final_answer"] or "")[:200],
        unread=not user_present,
    )
    if not user_present:
        try:
            from services.suggestions_service import notify_user

            notif_title = (
                "LogCore AI needs your input" if session_status != "idle" else "LogCore AI replied"
            )
            notify_user(
                current_user["name"],
                notif_title,
                f"{title}: {(result['final_answer'] or '')[:150]}",
                action={"type": "open_chat", "chat_id": req.chat_id},
                url="/chat",
            )
        except Exception:
            pass  # notification delivery must never break the chat response

    response_payload = {
        "response": result["final_answer"],
        "steps": result["steps"],
        "mode": result["status"],
        "chat_id": req.chat_id,
    }
    if result["status"] in ("awaiting_approval", "awaiting_answer"):
        response_payload["run_id"] = result["id"]
    return response_payload


class SaveMemoryRequest(BaseModel):
    history: list[HistoryMessage] = Field(..., min_length=1, max_length=50)
    target: Literal["short", "long"] = "short"


@router.post("/save-memory")
async def save_memory(
    req: SaveMemoryRequest,
    current_user: dict = Depends(_require_chat),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_memory_limit),
):
    if not is_ai_configured():
        raise HTTPException(status_code=503, detail="AI not configured.")

    usage = ai_usage_service.check_usage(current_user["name"])
    if usage["status"] == "blocked":
        raise HTTPException(status_code=402, detail="AI usage limit reached for this period.")

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
        user_name=current_user["name"],
        workspace=workspace,
    )
    ai_usage_service.record_message(current_user["name"], workspace)

    fname = "Long_Term_Memory.md" if req.target == "long" else "Short_Term_Memory.md"
    mem_path = ws_path(current_user["name"], workspace) / fname
    today = today_for_user(current_user["name"]).isoformat()

    existing = mem_path.read_text() if mem_path.exists() else ""
    if len(existing.encode()) >= _MEMORY_MAX_BYTES:
        raise HTTPException(
            status_code=413, detail="Memory file is full. Clear some entries before saving more."
        )

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
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_save_limit),
):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    user_tz = current_user.get("timezone", "UTC")
    try:
        now = datetime.now(ZoneInfo(user_tz))
    except Exception:
        now = datetime.now(ZoneInfo("UTC"))

    chats_dir = ws_path(current_user["name"], workspace) / "Chats"
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
                existing_title = target.open().readline().strip().lstrip("# ")
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
def list_saved_chats(
    current_user: dict = Depends(_require_chat),
    workspace: str = Depends(get_workspace),
):
    chats_dir = ws_path(current_user["name"], workspace) / "Chats"
    if not chats_dir.exists():
        return []
    files = sorted(chats_dir.glob("*.md"), reverse=True)
    result = []
    for f in files:
        # Read only the first line to get the title cheaply
        try:
            first_line = f.open().readline().strip().lstrip("# ")
        except Exception:
            first_line = f.stem
        result.append({"filename": f.name, "path": f"Chats/{f.name}", "title": first_line})
    return result


@router.delete("/saved/{filename}")
def delete_saved_chat(
    filename: str,
    current_user: dict = Depends(_require_chat),
    workspace: str = Depends(get_workspace),
):
    chats_dir = ws_path(current_user["name"], workspace) / "Chats"
    target = (chats_dir / filename).resolve()
    if not target.is_relative_to(chats_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Chat not found")
    target.unlink()
    agent_service.delete_session_by_filename(current_user["name"], workspace, filename)
    return {"ok": True}


@router.get("/sessions")
def list_sessions(
    current_user: dict = Depends(_require_chat), workspace: str = Depends(get_workspace)
):
    """One entry per conversation — the sidebar's real source, in place of
    /saved's plain filename listing: carries status (idle/awaiting_approval/
    awaiting_answer/running) and unread, not just a title."""
    return agent_service.load_sessions(current_user["name"], workspace)


@router.post("/sessions/{chat_id}/read")
def mark_session_read(
    chat_id: str,
    current_user: dict = Depends(_require_chat),
    workspace: str = Depends(get_workspace),
):
    agent_service.mark_session_read(current_user["name"], workspace, chat_id)
    return {"ok": True}


@router.get("/pending/{chat_id}")
def get_pending(chat_id: str, current_user: dict = Depends(_require_chat)):
    """The live pending_write/pending_question/pending_plan card for one
    conversation, if it currently has one (2026-08-15) — reopening a saved
    chat previously reloaded the plain text fine but lost the interactive
    approval/question/plan card entirely, since the .md archive has no
    structured step data. Chat.jsx calls this when a session's own status
    (from GET /chat/sessions) is awaiting_approval/awaiting_answer, and
    re-attaches the result onto the last loaded message."""
    pending = agent_service.get_pending_turn_by_chat_id(current_user["name"], chat_id)
    if not pending:
        return None
    # pending["mode"] is the chat MODE (approve/plan/auto/research) — the
    # frontend's message.mode field is the pause STATUS instead (matching
    # what a live response's `mode: result["status"]` already carries), so
    # it's derived from `kind` here rather than confusingly reusing "mode".
    status = "awaiting_answer" if pending["kind"] == "question" else "awaiting_approval"
    return {"run_id": pending["run_id"], "mode": status, "steps": pending["steps"]}


class PresenceRequest(BaseModel):
    chat_id: str = Field(..., max_length=64)


@router.post("/presence")
def ping_presence(
    req: PresenceRequest,
    current_user: dict = Depends(_require_chat),
    _rl: None = Depends(_presence_limit),
):
    """Chat.jsx calls this on mount/switch and on an interval while the tab
    is open and visible, showing this exact chat_id — lets the completion
    handler above skip a redundant notification when the user is still
    right there watching it finish (2026-08-15). See
    agent_service.is_chat_present for the staleness window."""
    agent_service.record_chat_presence(current_user["name"], req.chat_id)
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
