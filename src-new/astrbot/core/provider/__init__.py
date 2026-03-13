"""旧版 ``astrbot.core.provider`` 兼容入口。"""

from .entities import (
    LLMResponse,
    Personality,
    ProviderMetaData,
    ProviderRequest,
    ProviderType,
    RerankResult,
)
from .provider import EmbeddingProvider, Provider, RerankProvider, STTProvider

__all__ = [
    "EmbeddingProvider",
    "LLMResponse",
    "Personality",
    "Provider",
    "ProviderMetaData",
    "ProviderRequest",
    "ProviderType",
    "RerankProvider",
    "RerankResult",
    "STTProvider",
]
