import aiohttp

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


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

        proxy = provider_config.get("proxy", "")
        self.proxy = proxy
        if proxy:
            logger.info(f"[Ollama Embedding] Using proxy: {proxy}")

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
            except (ValueError, TypeError):
                pass
        return payload

    async def get_embedding(self, text: str) -> list[float]:
        embeddings = await self.get_embeddings([text])
        return embeddings[0] if embeddings else []

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        client = await self._get_client()
        if not client or client.closed:
            raise Exception("[Ollama Embedding] Client session not initialized")

        payload = self._build_payload(text)
        request_url = f"{self.base_url}/api/embed"

        try:
            async with client.post(
                request_url, json=payload, proxy=self.proxy or None
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"[Ollama Embedding] API Error: {response.status} - {error_text}"
                    )
                    raise Exception(
                        f"Ollama Embedding API request failed: HTTP {response.status} - {error_text}"
                    )

                response_data = await response.json()
                embeddings = response_data.get("embeddings", [])

                if not embeddings:
                    raise Exception(
                        f"[Ollama Embedding] No embeddings returned: {response_data}"
                    )

                return embeddings

        except aiohttp.ClientError as e:
            logger.error(f"[Ollama Embedding] Network error: {e}")
            raise
        except Exception as e:
            logger.error(f"[Ollama Embedding] Error: {e}", exc_info=True)
            raise

    def get_dim(self) -> int:
        if "embedding_dimensions" in self.provider_config:
            try:
                return int(self.provider_config["embedding_dimensions"])
            except (ValueError, TypeError):
                logger.warning(
                    f"embedding_dimensions in embedding configs is not a valid integer: "
                    f"'{self.provider_config['embedding_dimensions']}', ignored."
                )
        return 0

    async def terminate(self):
        if self.client and not self.client.closed:
            await self.client.close()
            self.client = None
