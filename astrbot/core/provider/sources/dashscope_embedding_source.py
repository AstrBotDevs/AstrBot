import httpx
from openai import AsyncOpenAI

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "dashscope_embedding",
    "DashScope text-embedding-v4 Embedding Provider",
    provider_type=ProviderType.EMBEDDING,
)
class DashscopeEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        proxy = provider_config.get("proxy", "")
        provider_id = provider_config.get("id", "unknown_id")
        http_client = None
        if proxy:
            logger.info(f"[DashScope Embedding] {provider_id} Using proxy: {proxy}")
            http_client = httpx.AsyncClient(proxy=proxy)
        api_base = (
            provider_config.get(
                "embedding_api_base",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            .strip()
            .removesuffix("/")
            .removesuffix("/embeddings")
        )
        if api_base and not api_base.endswith("/v1") and not api_base.endswith("/v4"):
            api_base = api_base + "/v1"
        logger.info(f"[DashScope Embedding] {provider_id} Using API Base: {api_base}")
        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=api_base,
            timeout=int(provider_config.get("timeout", 20)),
            http_client=http_client,
        )
        self.model = provider_config.get("embedding_model", "text-embedding-v4")

    async def get_embedding(self, text: str) -> list[float]:
        kwargs = self._embedding_kwargs()
        embedding = await self.client.embeddings.create(
            input=text,
            model=self.model,
            **kwargs,
        )
        if not embedding.data:
            raise Exception("DashScope API returned no embedding data.")
        return embedding.data[0].embedding

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        kwargs = self._embedding_kwargs()
        embeddings = await self.client.embeddings.create(
            input=text,
            model=self.model,
            **kwargs,
        )
        return [item.embedding for item in embeddings.data]

    def _embedding_kwargs(self) -> dict:
        kwargs = {}
        if "embedding_dimensions" in self.provider_config:
            try:
                kwargs["dimensions"] = int(self.provider_config["embedding_dimensions"])
            except (ValueError, TypeError):
                logger.warning(
                    f"embedding_dimensions in embedding configs is not a valid integer: '{self.provider_config['embedding_dimensions']}', ignored."
                )
        return kwargs

    def get_dim(self) -> int:
        if "embedding_dimensions" in self.provider_config:
            try:
                return int(self.provider_config["embedding_dimensions"])
            except (ValueError, TypeError):
                logger.warning(
                    f"embedding_dimensions in embedding configs is not a valid integer: '{self.provider_config['embedding_dimensions']}', ignored."
                )
        return 1024

    async def terminate(self):
        if self.client:
            await self.client.close()
