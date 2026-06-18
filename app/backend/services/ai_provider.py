"""AI provider abstraction — swap providers by changing AI_PROVIDER in .env."""
import asyncio

from config import settings


async def chat_completion(system: str, messages: list[dict], max_tokens: int = 1024) -> str:
    """Send a chat request to the configured AI provider and return the response text.

    Runs the synchronous provider call in a thread so the event loop is never blocked.
    Provider implementations stay synchronous — add new ones in _dispatch().
    """
    return await asyncio.to_thread(_dispatch, system, messages, max_tokens)


def _dispatch(system: str, messages: list[dict], max_tokens: int) -> str:
    if settings.ai_provider == "anthropic":
        return _anthropic(system, messages, max_tokens)
    raise ValueError(
        f"Unsupported AI_PROVIDER: '{settings.ai_provider}'. "
        "Currently supported: 'anthropic'"
    )


def _anthropic(system: str, messages: list[dict], max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.ai_model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text
