"""Provider-facing SDK entities and typed proxy helpers."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass

from ..clients._proxy import CapabilityProxy
from .entities import ProviderMeta, ProviderType, RerankResult


@dataclass(slots=True)
class TTSAudioChunk:
    audio: bytes
    text: str | None = None


class _BaseProviderProxy:
    def __init__(self, proxy: CapabilityProxy, meta: ProviderMeta) -> None:
        self._proxy = proxy
        self._meta = meta

    @property
    def id(self) -> str:
        return self._meta.id

    @property
    def model(self) -> str | None:
        return self._meta.model

    @property
    def type(self) -> str:
        return self._meta.type

    @property
    def provider_type(self) -> ProviderType:
        return self._meta.provider_type

    def meta(self) -> ProviderMeta:
        return self._meta


class STTProvider(_BaseProviderProxy):
    async def get_text(self, audio_url: str) -> str:
        output = await self._proxy.call(
            "provider.stt.get_text",
            {"provider_id": self.id, "audio_url": str(audio_url)},
        )
        return str(output.get("text", ""))


class TTSProvider(_BaseProviderProxy):
    def __init__(
        self,
        proxy: CapabilityProxy,
        meta: ProviderMeta,
        *,
        supports_stream: bool = False,
    ) -> None:
        super().__init__(proxy, meta)
        self._supports_stream = supports_stream

    async def get_audio(self, text: str) -> str:
        output = await self._proxy.call(
            "provider.tts.get_audio",
            {"provider_id": self.id, "text": str(text)},
        )
        return str(output.get("audio_path", ""))

    def support_stream(self) -> bool:
        return self._supports_stream

    async def get_audio_stream(
        self,
        text: str | AsyncIterable[str],
    ) -> AsyncIterator[TTSAudioChunk]:
        payload = await self._build_stream_payload(text)
        async for chunk in self._proxy.stream("provider.tts.get_audio_stream", payload):
            audio_base64 = str(chunk.get("audio_base64", ""))
            yield TTSAudioChunk(
                audio=base64.b64decode(audio_base64) if audio_base64 else b"",
                text=(
                    str(chunk.get("text")) if chunk.get("text") is not None else None
                ),
            )

    async def _build_stream_payload(
        self,
        text: str | AsyncIterable[str],
    ) -> dict[str, object]:
        payload: dict[str, object] = {"provider_id": self.id}
        if isinstance(text, str):
            payload["text"] = text
            return payload
        payload["text_chunks"] = [str(item) async for item in text]
        return payload


class EmbeddingProvider(_BaseProviderProxy):
    async def get_embedding(self, text: str) -> list[float]:
        output = await self._proxy.call(
            "provider.embedding.get_embedding",
            {"provider_id": self.id, "text": str(text)},
        )
        embedding = output.get("embedding")
        if not isinstance(embedding, list):
            return []
        return [float(item) for item in embedding]

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        output = await self._proxy.call(
            "provider.embedding.get_embeddings",
            {
                "provider_id": self.id,
                "texts": [str(item) for item in texts],
            },
        )
        embeddings = output.get("embeddings")
        if not isinstance(embeddings, list):
            return []
        return [
            [float(value) for value in item]
            for item in embeddings
            if isinstance(item, list)
        ]

    async def get_dim(self) -> int:
        output = await self._proxy.call(
            "provider.embedding.get_dim",
            {"provider_id": self.id},
        )
        return int(output.get("dim", 0))


class RerankProvider(_BaseProviderProxy):
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        output = await self._proxy.call(
            "provider.rerank.rerank",
            {
                "provider_id": self.id,
                "query": str(query),
                "documents": [str(item) for item in documents],
                "top_n": top_n,
            },
        )
        results = output.get("results")
        if not isinstance(results, list):
            return []
        return [
            RerankResult.from_payload(item)
            for item in results
            if isinstance(item, dict)
        ]


ProviderProxy = STTProvider | TTSProvider | EmbeddingProvider | RerankProvider


def provider_proxy_from_meta(
    proxy: CapabilityProxy,
    meta: ProviderMeta | None,
    *,
    tts_supports_stream: bool | None = None,
) -> ProviderProxy | None:
    if meta is None:
        return None
    if meta.provider_type == ProviderType.SPEECH_TO_TEXT:
        return STTProvider(proxy, meta)
    if meta.provider_type == ProviderType.TEXT_TO_SPEECH:
        return TTSProvider(
            proxy,
            meta,
            supports_stream=bool(tts_supports_stream),
        )
    if meta.provider_type == ProviderType.EMBEDDING:
        return EmbeddingProvider(proxy, meta)
    if meta.provider_type == ProviderType.RERANK:
        return RerankProvider(proxy, meta)
    return None


__all__ = [
    "EmbeddingProvider",
    "ProviderMeta",
    "ProviderProxy",
    "ProviderType",
    "RerankProvider",
    "RerankResult",
    "STTProvider",
    "TTSAudioChunk",
    "TTSProvider",
    "provider_proxy_from_meta",
]
