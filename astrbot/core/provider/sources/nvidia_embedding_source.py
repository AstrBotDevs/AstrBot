import asyncio
import math

import aiohttp

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter

_REQUEST_ERROR = "NVIDIA embedding request failed"


@register_provider_adapter(
    "nvidia_embedding",
    "NVIDIA NIM Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class NvidiaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

        self.api_key = provider_config.get("embedding_api_key", "")
        self.base_url = (
            provider_config.get(
                "embedding_api_base", "https://integrate.api.nvidia.com/v1"
            )
            .rstrip("/")
            .removesuffix("/embeddings")
        )
        self.timeout = int(provider_config.get("timeout", 20))
        self.model = provider_config.get(
            "embedding_model", "nvidia/nemotron-3-embed-1b"
        )
        self.input_type = provider_config.get("input_type", "passage")

        from astrbot.core.utils.proxy_route import resolve_proxy_route

        self._route = resolve_proxy_route(local_config=provider_config)
        self.proxy = self._route.proxy_url or ""

        self.client = None
        self.set_model(self.model)

    async def _get_client(self):
        if self.client is None or self.client.closed:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.client = aiohttp.ClientSession(
                headers=headers,
                timeout=timeout,
                trust_env=False,
            )
        return self.client

    def _build_payload(self, text: str | list[str]) -> dict:
        if isinstance(text, str):
            input_text = [text]
        else:
            input_text = text

        return {
            "input": input_text,
            "model": self.model,
            "input_type": self.input_type,
            "encoding_format": "float",
        }

    def _parse_response(
        self, response_data: dict, expected_count: int | None = None
    ) -> list[list[float]]:
        data = response_data.get("data")
        if not isinstance(data, list):
            raise ValueError("NVIDIA embedding response data must be a list")
        if data and all(
            isinstance(item, dict) and isinstance(item.get("index"), int)
            for item in data
        ):
            data = sorted(data, key=lambda item: item["index"])

        embeddings: list[list[float]] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("NVIDIA embedding response item must be an object")
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise ValueError("NVIDIA embedding response contains an empty vector")
            vector = [float(value) for value in embedding]
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("NVIDIA embedding response contains non-finite values")
            embeddings.append(vector)

        if expected_count is not None and len(embeddings) != expected_count:
            raise ValueError("NVIDIA embedding response count does not match input")
        return embeddings

    async def get_embedding(self, text: str) -> list[float]:
        embeddings = await self.get_embeddings([text])
        return embeddings[0] if embeddings else []

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        if not text:
            return []

        client = await self._get_client()
        if not client or client.closed:
            logger.error("[NVIDIA Embedding] Client session not initialized")
            raise RuntimeError(_REQUEST_ERROR)

        payload = self._build_payload(text)
        request_url = f"{self.base_url}/embeddings"

        try:
            async with client.post(
                request_url, json=payload, proxy=self.proxy or None
            ) as response:
                if response.status != 200:
                    logger.error(
                        "[NVIDIA Embedding] API request failed with status %s",
                        response.status,
                    )
                    raise RuntimeError(_REQUEST_ERROR)

                response_data = await response.json()
                if not isinstance(response_data, dict):
                    raise ValueError("NVIDIA embedding response must be an object")
                embeddings = self._parse_response(
                    response_data, expected_count=len(text)
                )

                usage = response_data.get("usage", {})
                if isinstance(usage, dict):
                    try:
                        total_tokens = int(usage.get("total_tokens", 0))
                    except TypeError, ValueError:
                        total_tokens = 0
                    if total_tokens > 0:
                        logger.debug("[NVIDIA Embedding] Token usage: %d", total_tokens)

                return embeddings

        except asyncio.CancelledError:
            raise
        except aiohttp.ClientError as exc:
            logger.error("[NVIDIA Embedding] Network failure: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None
        except Exception as exc:
            logger.error("[NVIDIA Embedding] Request failed: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None

    async def terminate(self):
        client = self.client
        self.client = None
        if client is None or client.closed:
            return
        try:
            await client.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "[NVIDIA Embedding] Client close failed: %s", safe_error("", exc)
            )
