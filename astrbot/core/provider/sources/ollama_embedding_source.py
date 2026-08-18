import asyncio
import math

import aiohttp

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter

_REQUEST_ERROR = "Ollama embedding request failed"


@register_provider_adapter(
    "ollama_embedding",
    "Ollama Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

        self.base_url = (
            provider_config.get("embedding_api_base", "http://localhost:11434")
            .rstrip("/")
            .removesuffix("/api/embed")
        )
        self.timeout = int(provider_config.get("timeout", 60))
        self.model = provider_config.get("embedding_model", "nomic-embed-text")

        from astrbot.core.utils.proxy_route import resolve_proxy_route

        self._route = resolve_proxy_route(local_config=provider_config)
        self.proxy = self._route.proxy_url or ""

        self.client = None
        self.set_model(self.model)

    async def _get_client(self):
        if self.client is None or self.client.closed:
            headers = {
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

    def _build_payload(self, text: list[str]) -> dict:
        payload = {
            "model": self.model,
            "input": text,
        }
        if "embedding_dimensions" in self.provider_config:
            try:
                dimensions = int(self.provider_config["embedding_dimensions"])
                if dimensions > 0:
                    payload["dimensions"] = dimensions
            except ValueError, TypeError:
                pass
        return payload

    async def get_embedding(self, text: str) -> list[float]:
        embeddings = await self.get_embeddings([text])
        return embeddings[0] if embeddings else []

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        if not text:
            return []

        client = await self._get_client()
        if not client or client.closed:
            logger.error("[Ollama Embedding] Client session not initialized")
            raise RuntimeError(_REQUEST_ERROR)

        payload = self._build_payload(text)
        request_url = f"{self.base_url}/api/embed"

        try:
            async with client.post(
                request_url, json=payload, proxy=self.proxy or None
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Ollama embedding HTTP status {response.status}"
                    )

                response_data = await response.json()
                if not isinstance(response_data, dict):
                    raise ValueError("Ollama embedding response must be an object")
                embeddings = response_data.get("embeddings", [])

                if not isinstance(embeddings, list) or len(embeddings) != len(text):
                    raise ValueError("Ollama embedding response has invalid dimensions")

                normalized_embeddings: list[list[float]] = []
                for embedding in embeddings:
                    if not isinstance(embedding, list) or not embedding:
                        raise ValueError(
                            "Ollama embedding response contains an empty vector"
                        )
                    vector = [float(value) for value in embedding]
                    if not all(math.isfinite(value) for value in vector):
                        raise ValueError(
                            "Ollama embedding response contains non-finite values"
                        )
                    normalized_embeddings.append(vector)

                return normalized_embeddings

        except asyncio.CancelledError:
            raise
        except aiohttp.ClientError as exc:
            logger.error("[Ollama Embedding] Network failure: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None
        except Exception as exc:
            logger.error("[Ollama Embedding] Request failed: %s", safe_error("", exc))
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
                "[Ollama Embedding] Client close failed: %s", safe_error("", exc)
            )
