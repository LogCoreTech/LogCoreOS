"""AI provider abstraction — swap providers without restarting the server.

Runtime config is read from {brain_path}/ai_settings.json on every call,
so admin UI changes take effect immediately without a restart.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from config import settings

logger = logging.getLogger("logcore.ai_provider")


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class AgentResponse:
    stop_reason: str  # "tool_use" | "end_turn" | "max_tokens"
    text: str
    tool_calls: list[ToolCall]
    raw_content: list  # Anthropic-format blocks; used to continue message history
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Runtime config helpers
# ---------------------------------------------------------------------------


def _load_ai_settings() -> dict:
    """Load runtime AI config from brain/ai_settings.json; returns {} if absent."""
    path = settings.brain_path / "ai_settings.json"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _get_config() -> dict:
    """Merge static settings with runtime overrides (runtime wins)."""
    base = vars(settings).copy()
    # vars(settings) may include Path objects — convert brain_path for safety
    base["brain_path"] = str(base.get("brain_path", ""))
    merged = {**base, **_load_ai_settings()}
    # Demo cost protection: force the cheap model regardless of whatever an admin
    # configured in ai_settings.json — a public demo takes unattended registrations,
    # so this can't be an opt-in the admin has to remember. Anthropic-only; a demo
    # instance running the openai provider isn't a case worth guarding here.
    if merged.get("demo_mode") and merged.get("ai_provider", "anthropic") == "anthropic":
        merged["ai_model"] = merged.get("demo_ai_model", "claude-haiku-4-6")
    return merged


def is_ai_configured() -> bool:
    cfg = _get_config()
    provider = cfg.get("ai_provider", "anthropic")
    if provider == "anthropic":
        return bool(cfg.get("anthropic_api_key") or cfg.get("ai_api_key"))
    # openai-compatible: key is optional when a local base_url is set (e.g. Ollama)
    return bool(cfg.get("ai_api_key")) or bool(cfg.get("ai_base_url"))


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def chat_completion(
    system: str,
    messages: list[dict],
    max_tokens: int = 1024,
    *,
    user_name: str,
    workspace: str = "personal",
) -> str:
    """Send a chat request and return the text response."""
    text, input_tokens, output_tokens = await asyncio.to_thread(
        _dispatch, system, messages, max_tokens
    )
    _record(user_name, workspace, input_tokens, output_tokens)
    return text


async def agent_completion(
    system: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 4096,
    *,
    user_name: str,
    workspace: str = "personal",
) -> AgentResponse:
    """Send a tool-enabled request and return an AgentResponse."""
    response = await asyncio.to_thread(_dispatch_agent, system, messages, tools, max_tokens)
    _record(user_name, workspace, response.input_tokens, response.output_tokens)
    return response


def _record(user_name: str, workspace: str, input_tokens: int, output_tokens: int) -> None:
    """Best-effort usage metering — must never break a real AI call."""
    try:
        from services.ai_usage_service import record_tokens

        record_tokens(user_name, workspace, input_tokens, output_tokens)
    except Exception:
        logger.exception("ai_usage_service.record_tokens failed for %s", user_name)


# ---------------------------------------------------------------------------
# Synchronous dispatch
# ---------------------------------------------------------------------------


def _dispatch(system: str, messages: list[dict], max_tokens: int) -> tuple[str, int, int]:
    cfg = _get_config()
    provider = cfg.get("ai_provider", "anthropic")
    if provider == "anthropic":
        return _anthropic(system, messages, max_tokens, cfg)
    if provider == "openai":
        return _openai(system, messages, max_tokens, cfg)
    raise ValueError(f"Unsupported ai_provider: '{provider}'")


def _dispatch_agent(
    system: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
) -> AgentResponse:
    cfg = _get_config()
    provider = cfg.get("ai_provider", "anthropic")
    if provider == "anthropic":
        return _anthropic_agent(system, messages, tools, max_tokens, cfg)
    if provider == "openai":
        return _openai_agent(system, messages, tools, max_tokens, cfg)
    raise ValueError(f"Unsupported ai_provider: '{provider}'")


# ---------------------------------------------------------------------------
# Anthropic implementation
# ---------------------------------------------------------------------------


def _anthropic(
    system: str, messages: list[dict], max_tokens: int, cfg: dict
) -> tuple[str, int, int]:
    import anthropic

    key = cfg.get("ai_api_key") or cfg.get("anthropic_api_key")
    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model=cfg.get("ai_model", "claude-sonnet-4-6"),
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    return response.content[0].text, input_tokens, output_tokens


def _anthropic_agent(
    system: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
    cfg: dict,
) -> AgentResponse:
    import anthropic

    key = cfg.get("ai_api_key") or cfg.get("anthropic_api_key")
    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model=cfg.get("ai_model", "claude-sonnet-4-6"),
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        tools=tools,
    )

    text = ""
    tool_calls: list[ToolCall] = []
    raw_content: list = []

    for block in response.content:
        if block.type == "text":
            text = block.text
            raw_content.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))
            raw_content.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )

    usage = getattr(response, "usage", None)
    return AgentResponse(
        stop_reason=response.stop_reason,
        text=text,
        tool_calls=tool_calls,
        raw_content=raw_content,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    )


# ---------------------------------------------------------------------------
# OpenAI-compatible implementation
# ---------------------------------------------------------------------------


def _openai(system: str, messages: list[dict], max_tokens: int, cfg: dict) -> tuple[str, int, int]:
    import openai as _openai

    client = _openai.OpenAI(
        api_key=cfg.get("ai_api_key") or "ollama",
        base_url=cfg.get("ai_base_url") or None,
    )
    oai_messages = [{"role": "system", "content": system}] + messages
    response = client.chat.completions.create(
        model=cfg.get("ai_model", "gpt-4o"),
        max_tokens=max_tokens,
        messages=oai_messages,
    )
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    return response.choices[0].message.content or "", input_tokens, output_tokens


def _openai_agent(
    system: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
    cfg: dict,
) -> AgentResponse:
    import openai as _openai

    client = _openai.OpenAI(
        api_key=cfg.get("ai_api_key") or "ollama",
        base_url=cfg.get("ai_base_url") or None,
    )

    # Translate Anthropic-format messages → OpenAI format
    oai_messages = [{"role": "system", "content": system}]
    for msg in messages:
        oai_messages.extend(_anthropic_msg_to_openai(msg))

    # Translate tool schema: input_schema → parameters
    oai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]

    response = client.chat.completions.create(
        model=cfg.get("ai_model", "gpt-4o"),
        max_tokens=max_tokens,
        messages=oai_messages,
        tools=oai_tools,
        tool_choice="auto",
    )

    choice = response.choices[0]
    msg = choice.message

    text = msg.content or ""
    tool_calls: list[ToolCall] = []
    raw_content: list = []

    if text:
        raw_content.append({"type": "text", "text": text})

    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                input_data = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                input_data = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=input_data))
            raw_content.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": input_data,
                }
            )

    stop_reason = "end_turn"
    if choice.finish_reason == "tool_calls":
        stop_reason = "tool_use"
    elif choice.finish_reason == "length":
        stop_reason = "max_tokens"

    usage = getattr(response, "usage", None)
    return AgentResponse(
        stop_reason=stop_reason,
        text=text,
        tool_calls=tool_calls,
        raw_content=raw_content,
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
    )


def _anthropic_msg_to_openai(msg: dict) -> list[dict]:
    """Translate one Anthropic-format message → one or more OpenAI-format messages."""
    role = msg["role"]
    content = msg["content"]

    if isinstance(content, str):
        return [{"role": role, "content": content}]

    if isinstance(content, list):
        if role == "assistant":
            text_parts = [b["text"] for b in content if b.get("type") == "text" and b.get("text")]
            oai_tool_calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {
                        "name": b["name"],
                        "arguments": json.dumps(b["input"]),
                    },
                }
                for b in content
                if b.get("type") == "tool_use"
            ]
            oai_msg: dict = {
                "role": "assistant",
                "content": " ".join(text_parts) or None,
            }
            if oai_tool_calls:
                oai_msg["tool_calls"] = oai_tool_calls
            return [oai_msg]

        if role == "user":
            result = []
            for block in content:
                if block.get("type") == "tool_result":
                    rc = block["content"]
                    if not isinstance(rc, str):
                        rc = json.dumps(rc)
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": rc,
                        }
                    )
                elif block.get("type") == "text":
                    result.append({"role": "user", "content": block["text"]})
            return result

    return [{"role": role, "content": str(content)}]
