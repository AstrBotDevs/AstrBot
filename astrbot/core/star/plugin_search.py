from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_PLUGIN_SEARCH_LIMIT = 6


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def get_plugin_search_result_limit(
    config: Mapping[str, Any] | None = None,
    *,
    override: int | None = None,
) -> int:
    if override is not None:
        return max(1, int(override))
    if config is None:
        return DEFAULT_PLUGIN_SEARCH_LIMIT
    provider_settings = config.get("provider_settings", {})
    extension_cfg = provider_settings.get("extension_install", {})
    raw_limit = extension_cfg.get("search_result_limit", DEFAULT_PLUGIN_SEARCH_LIMIT)
    try:
        return max(1, int(raw_limit))
    except (TypeError, ValueError):
        return DEFAULT_PLUGIN_SEARCH_LIMIT


def normalize_plugin_record(
    item: Mapping[str, Any],
    *,
    fallback_name: str = "",
) -> dict[str, Any]:
    normalized = dict(item)
    name = _normalize_text(
        normalized.get("name")
        or normalized.get("display_name")
        or normalized.get("trimmedName")
        or fallback_name
    )
    normalized["name"] = name
    normalized["display_name"] = _normalize_text(normalized.get("display_name"))
    normalized["desc"] = _normalize_text(
        normalized.get("desc") or normalized.get("description")
    )
    normalized["author"] = _normalize_text(normalized.get("author"))
    normalized["repo"] = _normalize_text(normalized.get("repo"))
    return normalized


def _match_bucket(value: str, query: str) -> int | None:
    if not value:
        return None
    lowered = value.lower()
    if lowered == query:
        return 0
    if lowered.startswith(query):
        return 1
    if query in lowered:
        return 2
    return None


def _score_record(record: Mapping[str, Any], query: str) -> tuple[int, int, str] | None:
    primary_fields = (
        _normalize_text(record.get("name")),
        _normalize_text(record.get("display_name")),
    )
    secondary_fields = (
        _normalize_text(record.get("desc")),
        _normalize_text(record.get("author")),
        _normalize_text(record.get("repo")),
    )

    best_primary = min(
        (
            bucket
            for value in primary_fields
            if (bucket := _match_bucket(value, query)) is not None
        ),
        default=None,
    )
    if best_primary is not None:
        return (0, best_primary, primary_fields[0].lower())

    best_secondary = min(
        (
            bucket
            for value in secondary_fields
            if (bucket := _match_bucket(value, query)) is not None
        ),
        default=None,
    )
    if best_secondary is not None:
        return (1, best_secondary, primary_fields[0].lower())
    return None


def search_plugin_records(
    records: Sequence[Mapping[str, Any]],
    query: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    normalized_query = query.strip().lower()
    normalized_records = [
        normalize_plugin_record(record)
        for record in records
        if isinstance(record, Mapping)
    ]
    if not normalized_query:
        result = list(normalized_records)
    else:
        scored: list[tuple[tuple[int, int, str], int, dict[str, Any]]] = []
        for index, record in enumerate(normalized_records):
            score = _score_record(record, normalized_query)
            if score is None:
                continue
            scored.append((score, index, record))
        scored.sort(key=lambda item: (item[0], item[1]))
        result = [record for _, _, record in scored]

    if limit is None:
        return result
    return result[: max(1, limit)]


def _iter_market_records(raw_market: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(raw_market, Mapping):
        for key, value in raw_market.items():
            if not isinstance(value, Mapping):
                continue
            records.append(normalize_plugin_record(value, fallback_name=str(key)))
        return records
    if isinstance(raw_market, Sequence) and not isinstance(
        raw_market, (str, bytes, bytearray)
    ):
        for item in raw_market:
            if not isinstance(item, Mapping):
                continue
            records.append(normalize_plugin_record(item))
    return records


def search_plugin_market_records(
    raw_market: Any,
    query: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return search_plugin_records(_iter_market_records(raw_market), query, limit=limit)


def filter_plugin_market_payload(
    raw_market: Any,
    query: str,
    *,
    limit: int | None = None,
) -> Any:
    if isinstance(raw_market, Mapping):
        normalized_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for key, value in raw_market.items():
            if not isinstance(value, Mapping):
                continue
            normalized_pairs.append(
                (normalize_plugin_record(value, fallback_name=str(key)), dict(value))
            )
        normalized_results = search_plugin_records(
            [normalized for normalized, _ in normalized_pairs],
            query,
            limit=limit,
        )
        original_by_name = {
            normalized["name"]: original for normalized, original in normalized_pairs
        }
        return {
            item["name"]: original_by_name.get(item["name"], item)
            for item in normalized_results
        }
    if isinstance(raw_market, Sequence) and not isinstance(
        raw_market, (str, bytes, bytearray)
    ):
        normalized_pairs = []
        for item in raw_market:
            if not isinstance(item, Mapping):
                continue
            normalized_pairs.append((normalize_plugin_record(item), dict(item)))
        normalized_results = search_plugin_records(
            [normalized for normalized, _ in normalized_pairs],
            query,
            limit=limit,
        )
        original_by_name = {
            normalized["name"]: original for normalized, original in normalized_pairs
        }
        return [original_by_name.get(item["name"], item) for item in normalized_results]
    return raw_market
