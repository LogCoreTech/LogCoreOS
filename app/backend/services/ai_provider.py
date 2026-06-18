"""AI provider abstraction — swap providers by changing AI_PROVIDER in .env."""
from config import settings


async def chat_completion(system: str, messages: list[dict], max_tokens: int = 1024) -> str:
    """Send a chat request to the configured AI provider and return the response text."""
    if settings.ai_provider == "anthropic":
        return await _anthropic_async(system, messages, max_tokens)
    raise ValueError(
        f"Unsupported AI_PROVIDER: '{settings.ai_provider}'. "
        "Currently supported: 'anthropic'"
    )


async def _anthropic_async(system: str, messages: list[dict], max_tokens: int) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.ai_model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text
