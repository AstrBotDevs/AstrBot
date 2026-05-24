from __future__ import annotations

from typing import Any

from astrbot import logger

COMMON_MODEL_DIMENSIONS = {
    "bge-m3": 1024,
    "bge-large-en-v1.5": 1024,
    "bge-large-zh-v1.5": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def parse_configured_embedding_dimension(
    raw_dimension: Any,
    *,
    provider_label: str,
    provider_id: str,
) -> int | None:
    if raw_dimension in (None, ""):
        return None

    try:
        dimension = int(raw_dimension)
    except (TypeError, ValueError):
        logger.warning(
            "[%s] %s 的 embedding_dimensions 不是有效整数: %r",
            provider_label,
            provider_id,
            raw_dimension,
        )
        return None

    return dimension if dimension > 0 else None


def infer_embedding_dimension_from_model(model_name: Any) -> int | None:
    normalized_model = str(model_name or "").strip().lower()
    for model_key, dimension in COMMON_MODEL_DIMENSIONS.items():
        if model_key in normalized_model:
            return dimension
    return None
