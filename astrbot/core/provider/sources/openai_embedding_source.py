import asyncio
import math
import re
from urllib.parse import urlparse

import httpx2
from openai import AsyncOpenAI

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter

_REQUEST_ERROR = "OpenAI embedding request failed"


def _normalize_api_base(api_base: str) -> str:
    api_base = api_base.strip().removesuffix("/").removesuffix("/embeddings")
    if api_base and not re.search(r"/v\d+$", api_base):
        api_base = api_base + "/v1"
    return api_base


@register_provider_adapter(
    "openai_embedding",
    "OpenAI API Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        proxy = provider_config.get("proxy", "")
        http_client = None
        if proxy:
            logger.info("[OpenAI Embedding] Using configured proxy")
            http_client = httpx2.AsyncClient(proxy=proxy)
        api_base = _normalize_api_base(
            provider_config.get("embedding_api_base", "https://api.openai.com/v1")
        )
        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=api_base,
            timeout=int(provider_config.get("timeout", 20)),
            http_client=http_client,
        )
        self.model = provider_config.get("embedding_model", "text-embedding-3-small")
        self.set_model(self.model)

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入"""
        return (await self._request_embeddings(text))[0]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入"""
        if not text:
            return []
        return await self._request_embeddings(text)

    async def _request_embeddings(self, text: str | list[str]) -> list[list[float]]:
        """Request and validate one vector for each input text."""
        expected_count = 1 if isinstance(text, str) else len(text)
        try:
            client = self.client
            if client is None:
                raise RuntimeError(_REQUEST_ERROR)
            response = await client.embeddings.create(
                input=text,
                model=self.model,
                **self._embedding_kwargs(),
            )
            data = getattr(response, "data", None)
            if not isinstance(data, list) or len(data) != expected_count:
                raise ValueError("OpenAI embedding response has an invalid item count")

            vectors: list[list[float]] = []
            for item in data:
                embedding = getattr(item, "embedding", None)
                if not isinstance(embedding, list) or not embedding:
                    raise ValueError(
                        "OpenAI embedding response contains an empty vector"
                    )
                vector = [float(value) for value in embedding]
                if not all(math.isfinite(value) for value in vector):
                    raise ValueError(
                        "OpenAI embedding response contains non-finite values"
                    )
                vectors.append(vector)
            return vectors
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[OpenAI Embedding] Request failed: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None

    def _embedding_kwargs(self) -> dict:
        """Build optional embedding request parameters."""
        kwargs: dict[str, int] = {}
        dimensions_mode = self.provider_config.get("embedding_dimensions_mode", "auto")
        if dimensions_mode not in {"auto", "always", "never"}:
            logger.warning("Unknown embedding_dimensions_mode; using auto.")
            dimensions_mode = "auto"

        send_dimensions = dimensions_mode == "always"
        if dimensions_mode == "auto":
            api_base = _normalize_api_base(
                self.provider_config.get(
                    "embedding_api_base",
                    "https://api.openai.com/v1",
                )
                or "https://api.openai.com/v1"
            )
            parsed_api_base = urlparse(api_base)
            model_name = self.model.lower().rsplit("/", 1)[-1]
            send_dimensions = (
                parsed_api_base.scheme == "https"
                and parsed_api_base.hostname == "api.openai.com"
                and parsed_api_base.path.rstrip("/") == "/v1"
                and model_name.startswith("text-embedding-3")
            ) or (
                parsed_api_base.scheme == "https"
                and parsed_api_base.hostname == "api.siliconflow.cn"
                and model_name.startswith("qwen")
            )

        if send_dimensions and "embedding_dimensions" in self.provider_config:
            try:
                kwargs["dimensions"] = int(self.provider_config["embedding_dimensions"])
            except ValueError, TypeError:
                logger.warning(
                    "embedding_dimensions in embedding configs is not a valid integer; "
                    "ignored."
                )

        return kwargs

    async def terminate(self):
        client = self.client
        self.client = None
        if client is None:
            return
        try:
            await client.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "[OpenAI Embedding] Client close failed: %s", safe_error("", exc)
            )
