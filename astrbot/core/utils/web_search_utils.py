import json
import re
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
            f"Error: {provider_name} API Base URL must be a base host URL starting "
            f"with http:// or https:// (for example, {default}), not a full endpoint "
            f"path. Received: {normalized!r}.",
        )
    return normalized


def _iter_web_search_result_items(
    accumulated_parts: list[dict[str, Any]],
):
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
                if isinstance(item, dict):
                    yield item


def _extract_ref_indices(accumulated_text: str) -> list[str]:
    ref_indices: list[str] = []
    seen_indices: set[str] = set()

    for match in re.finditer(r"<ref>(.*?)</ref>", accumulated_text):
        ref_index = match.group(1).strip()
        if not ref_index or ref_index in seen_indices:
            continue
        ref_indices.append(ref_index)
        seen_indices.add(ref_index)

    return ref_indices


def collect_web_search_ref_items(
    accumulated_parts: list[dict[str, Any]],
    favicon_cache: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    web_search_refs: list[dict[str, Any]] = []
    seen_indices: set[str] = set()

    for item in _iter_web_search_result_items(accumulated_parts):
        ref_index = item.get("index")
        if not ref_index or ref_index in seen_indices:
            continue

        payload = {
            "index": ref_index,
            "url": item.get("url"),
            "title": item.get("title"),
            "snippet": item.get("snippet"),
        }
        if favicon_cache and payload["url"] in favicon_cache:
            payload["favicon"] = favicon_cache[payload["url"]]

        web_search_refs.append(payload)
        seen_indices.add(ref_index)

    return web_search_refs


def build_web_search_refs(
    accumulated_text: str,
    accumulated_parts: list[dict[str, Any]],
    favicon_cache: dict[str, str] | None = None,
) -> dict:
    ordered_refs = collect_web_search_ref_items(accumulated_parts, favicon_cache)
    if not ordered_refs:
        return {}

    refs_by_index = {ref["index"]: ref for ref in ordered_refs}
    ref_indices = _extract_ref_indices(accumulated_text)
    used_refs = [refs_by_index[idx] for idx in ref_indices if idx in refs_by_index]

    if not used_refs:
        used_refs = ordered_refs

    return {"used": used_refs}


def collect_web_search_results(accumulated_parts: list[dict[str, Any]]) -> dict:
    web_search_results = {}

    for ref in collect_web_search_ref_items(accumulated_parts):
        web_search_results[ref["index"]] = {
            "url": ref.get("url"),
            "title": ref.get("title"),
            "snippet": ref.get("snippet"),
        }

    return web_search_results
