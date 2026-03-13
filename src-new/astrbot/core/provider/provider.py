"""旧版 ``astrbot.core.provider.provider`` 兼容入口。"""

from __future__ import annotations

from typing import Any

from .entities import ProviderMetaData


class Provider:
    """旧版 Provider 基类占位。"""

    async def text_chat(self, *args, **kwargs):  # pragma: no cover - compat stub
        raise NotImplementedError("compat facade does not implement core providers")

    def meta(self) -> ProviderMetaData:  # pragma: no cover - compat stub
        raise NotImplementedError("compat facade does not implement core providers")

    def get_model(self) -> str:  # pragma: no cover - compat stub
        raise NotImplementedError("compat facade does not implement core providers")


class STTProvider(Provider):
    pass


class EmbeddingProvider(Provider):
    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("compat facade does not implement embeddings")

    async def get_embeddings_batch(
        self,
        texts: list[str],
        *,
        batch_size: int = 16,
        tasks_limit: int = 3,
        max_retries: int = 3,
        progress_callback: Any | None = None,
    ) -> list[list[float]]:
        raise NotImplementedError("compat facade does not implement embeddings")

    def get_dim(self) -> int:
        raise NotImplementedError("compat facade does not implement embeddings")


class RerankProvider(Provider):
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ):
        raise NotImplementedError("compat facade does not implement rerank")


__all__ = [
    "EmbeddingProvider",
    "Provider",
    "RerankProvider",
    "STTProvider",
]
