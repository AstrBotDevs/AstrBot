import asyncio
import math
from typing import cast

from google import genai
from google.genai import types

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter

_REQUEST_ERROR = "Gemini embedding request failed"


@register_provider_adapter(
    "gemini_embedding",
    "Google Gemini Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

        api_key: str = provider_config["embedding_api_key"]
        api_base: str = provider_config["embedding_api_base"]
        timeout: int = int(provider_config.get("timeout", 20))

        http_options = types.HttpOptions(timeout=timeout * 1000)
        if api_base:
            api_base = api_base.removesuffix("/")
            http_options.base_url = api_base
        from astrbot.core.utils.proxy_route import (
            httpx_client_kwargs,
            resolve_proxy_route,
        )

        route = resolve_proxy_route(local_config=provider_config)
        http_options.async_client_args = httpx_client_kwargs(route)

        self.client = genai.Client(api_key=api_key, http_options=http_options).aio

        self.model = provider_config.get(
            "embedding_model",
            "gemini-embedding-exp-03-07",
        )

    @staticmethod
    def _extract_embeddings(result: object, expected_count: int) -> list[list[float]]:
        embeddings = getattr(result, "embeddings", None)
        if not isinstance(embeddings, list) or len(embeddings) != expected_count:
            raise ValueError("Gemini returned an invalid embedding response")

        parsed_embeddings: list[list[float]] = []
        for embedding in embeddings:
            values = getattr(embedding, "values", None)
            if not isinstance(values, list):
                raise ValueError("Gemini returned invalid embedding values")
            try:
                parsed_values = [float(value) for value in values]
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Gemini returned invalid embedding values") from exc
            if not all(math.isfinite(value) for value in parsed_values):
                raise ValueError("Gemini returned invalid embedding values")
            parsed_embeddings.append(parsed_values)

        return parsed_embeddings

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入"""
        try:
            client = self.client
            if client is None:
                raise RuntimeError(_REQUEST_ERROR)
            result = await client.models.embed_content(
                model=self.model,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.get_dim(),
                ),
            )
            return self._extract_embeddings(result, expected_count=1)[0]
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Gemini embedding request failed: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入"""
        try:
            contents = cast(types.ContentListUnion, list(text))
            client = self.client
            if client is None:
                raise RuntimeError(_REQUEST_ERROR)
            result = await client.models.embed_content(
                model=self.model,
                contents=contents,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.get_dim(),
                ),
            )
            return self._extract_embeddings(result, expected_count=len(text))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Gemini embedding request failed: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None

    def get_dim(self) -> int:
        """获取向量的维度"""
        return int(self.provider_config.get("embedding_dimensions", 768))

    async def terminate(self) -> None:
        client = self.client
        self.client = None
        if client is None:
            return
        try:
            await client.aclose()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Gemini embedding client close failed: %s", safe_error("", exc)
            )
