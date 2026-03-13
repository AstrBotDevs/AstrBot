"""旧版 ``astrbot.core.provider.entities`` 兼容入口。"""

from __future__ import annotations

from dataclasses import dataclass

from astrbot.api.provider import (
    LLMResponse,
    Personality,
    ProviderMetaData,
    ProviderRequest,
    ProviderType,
)


@dataclass(slots=True)
class RerankResult:
    index: int
    relevance_score: float


__all__ = [
    "LLMResponse",
    "Personality",
    "ProviderMetaData",
    "ProviderRequest",
    "ProviderType",
    "RerankResult",
]
