"""
tools.py - Tool definitions and execution for LLM function calling.

Tools (no API keys required):
  get_current_time  - returns local date/time
  get_weather       - wttr.in (free, no key)
  web_search        - DuckDuckGo via duckduckgo-search package
  fetch_url         - fetches and cleans a webpage
"""

import json
import datetime
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling schema)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current local date, time, and day of week.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Get the current weather for a city or location. "
                "Returns temperature, condition, humidity, and wind."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or location (e.g. 'Hanoi', 'London, UK')",
                    }
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information. "
                "Returns the top results with title, URL, and snippet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and read the text content of a webpage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to fetch (must start with http:// or https://)",
                    }
                },
                "required": ["url"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def get_current_time(**_) -> str:
    now = datetime.datetime.now()
    return (
        f"Current time: {now.strftime('%H:%M:%S')}\n"
        f"Date: {now.strftime('%A, %d %B %Y')}"
    )


def get_weather(location: str, **_) -> str:
    try:
        url = f"https://wttr.in/{location}?format=j1"
        r = httpx.get(url, timeout=8, follow_redirects=True)
        r.raise_for_status()
        data = r.json()
        cur = data["current_condition"][0]
        area = data["nearest_area"][0]
        city = (area.get("areaName", [{}])[0].get("value", location))

        temp_c   = cur["temp_C"]
        feels_c  = cur["FeelsLikeC"]
        desc     = cur["weatherDesc"][0]["value"]
        humidity = cur["humidity"]
        wind_kph = cur["windspeedKmph"]
        wind_dir = cur["winddir16Point"]

        return (
            f"Weather in {city}:\n"
            f"  Condition : {desc}\n"
            f"  Temperature: {temp_c}°C (feels like {feels_c}°C)\n"
            f"  Humidity  : {humidity}%\n"
            f"  Wind      : {wind_kph} km/h {wind_dir}"
        )
    except Exception as exc:
        return f"Could not get weather for '{location}': {exc}"


def web_search(query: str, max_results: int = 5, **_) -> str:
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=int(max_results)):
                results.append(
                    f"Title: {r.get('title', '')}\n"
                    f"URL  : {r.get('href', '')}\n"
                    f"Snippet: {r.get('body', '')}"
                )
        if not results:
            return "No results found."
        return f"Search results for '{query}':\n\n" + "\n\n".join(results)
    except ImportError:
        return (
            "duckduckgo-search is not installed. "
            "Run: pip install duckduckgo-search"
        )
    except Exception as exc:
        return f"Search failed: {exc}"


def fetch_url(url: str, **_) -> str:
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        # Strip HTML tags simply
        import re
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text).strip()
        # Truncate to ~3000 chars to keep context manageable
        if len(text) > 3000:
            text = text[:3000] + "... [truncated]"
        return f"Content of {url}:\n\n{text}"
    except Exception as exc:
        return f"Could not fetch '{url}': {exc}"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    "get_current_time": get_current_time,
    "get_weather":      get_weather,
    "web_search":       web_search,
    "fetch_url":        fetch_url,
}


def parse_text_tool_call(content: str) -> dict | None:
    """
    Detect when a model outputs a tool call as plain text JSON instead of
    using the structured tool_calls API field.

    Matches patterns like:
      {"name": "get_current_time", "arguments": {}}
      {"name": "web_search", "arguments": {"query": "..."}}
    """
    import re

    # Try the whole content as JSON first
    stripped = content.strip()
    # Remove markdown code fences if present
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    stripped = stripped.strip()

    try:
        data = json.loads(stripped)
        if isinstance(data, dict) and "name" in data and data["name"] in _HANDLERS:
            return {"name": data["name"],
                    "arguments": data.get("arguments") or data.get("parameters") or {}}
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: regex scan for the pattern anywhere in the content
    pattern = (r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*'
               r'"(?:arguments|parameters)"\s*:\s*(\{[^}]*\})\s*\}')
    m = re.search(pattern, content, re.DOTALL)
    if m:
        name = m.group(1)
        if name in _HANDLERS:
            try:
                args = json.loads(m.group(2))
                return {"name": name, "arguments": args}
            except json.JSONDecodeError:
                return {"name": name, "arguments": {}}

    return None


def execute_tool(name: str, arguments: str | dict) -> str:
    """
    Execute a tool by name. Returns the result as a string.
    arguments can be a JSON string or already-parsed dict.
    """
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            args = {}
    else:
        args = arguments or {}

    handler = _HANDLERS.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    try:
        return handler(**args)
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return f"Tool error: {exc}"
