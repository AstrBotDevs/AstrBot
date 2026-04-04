import json
from typing import Any
from urllib.parse import urlparse

WEB_SEARCH_REFERENCE_TOOLS = (
    "web_search_tavily",
    "web_search_bocha",
    "web_search_exa",
    "exa_find_similar",
)


def normalize_web_search_base_url(
    base_url: str | None,
    *,
    default: str,
    provider_name: str,
) -> str:
    normalized = (base_url or "").strip()
    if not normalized:
        normalized = default
    normalized = normalized.rstrip("/")

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            f"Error: {provider_name} API Base URL must start with http:// or https://.",
        )
    return normalized


def collect_web_search_results(accumulated_parts: list[dict[str, Any]]) -> dict:
    web_search_results = {}

    for part in accumulated_parts:
        if part.get("type") != "tool_call" or not part.get("tool_calls"):
            continue

        for tool_call in part["tool_calls"]:
            if tool_call.get(
                "name"
            ) not in WEB_SEARCH_REFERENCE_TOOLS or not tool_call.get("result"):
                continue

            result = tool_call["result"]
            try:
                result_data = json.loads(result) if isinstance(result, str) else result
            except json.JSONDecodeError:
                continue

            if not isinstance(result_data, dict):
                continue

            for item in result_data.get("results", []):
                if not isinstance(item, dict):
                    continue
                if idx := item.get("index"):
                    web_search_results[idx] = {
                        "url": item.get("url"),
                        "title": item.get("title"),
                        "snippet": item.get("snippet"),
                    }

    return web_search_results
