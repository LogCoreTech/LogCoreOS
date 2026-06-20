"""Web search via Tavily API — used by the AI agent in research mode."""
import httpx
from config import settings
from services.file_service import brain_path, read_json


def get_tavily_key() -> str:
    """Read Tavily key from ai_settings.json (admin-set) falling back to env."""
    stored = read_json(brain_path() / "ai_settings.json", default={})
    return stored.get("tavily_api_key", "") or settings.tavily_api_key


def search(query: str, max_results: int = 5) -> list | dict:
    """
    Search the web via Tavily. Returns a list of result dicts or an error dict.
    Synchronous — safe to call from agent tool executors.
    """
    key = get_tavily_key()
    if not key:
        return {
            "error": (
                "Web search is not configured. Ask an admin to add a Tavily API key "
                "in the Admin panel (Admin → Web Search)."
            )
        }
    n = min(max(1, int(max_results)), 10)
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": key,
                "query": query,
                "max_results": n,
                "search_depth": "basic",
            },
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        return [
            {
                "title":   x.get("title", ""),
                "url":     x.get("url", ""),
                "content": (x.get("content") or x.get("snippet") or "")[:600],
            }
            for x in data.get("results", [])
        ]
    except httpx.HTTPStatusError as e:
        return {"error": f"Tavily returned {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"Web search failed: {e}"}
