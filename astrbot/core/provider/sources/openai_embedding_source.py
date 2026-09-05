import re
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


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
        provider_id = provider_config.get("id", "unknown_id")
        http_client = None
        if proxy:
            logger.info(f"[OpenAI Embedding] {provider_id} Using proxy: {proxy}")
            http_client = httpx.AsyncClient(proxy=proxy)
        api_base = _normalize_api_base(
            provider_config.get("embedding_api_base", "https://api.openai.com/v1")
        )
        logger.info(f"[OpenAI Embedding] {provider_id} Using API Base: {api_base}")
        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=api_base,
            timeout=int(provider_config.get("timeout", 20)),
            http_client=http_client,
        )
        self.model = provider_config.get("embedding_model", "text-embedding-3-small")

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入"""
        kwargs = self._embedding_kwargs()
        embedding = await self.client.embeddings.create(
            input=text,
            model=self.model,
            **kwargs,
        )
        return embedding.data[0].embedding

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入"""
        kwargs = self._embedding_kwargs()
        embeddings = await self.client.embeddings.create(
            input=text,
            model=self.model,
            **kwargs,
        )
        return [item.embedding for item in embeddings.data]

    def _embedding_kwargs(self) -> dict:
        """Build optional embedding request parameters."""
        kwargs = {}
        dimensions_mode = self.provider_config.get("embedding_dimensions_mode", "auto")
        if dimensions_mode not in {"auto", "always", "never"}:
            logger.warning(
                f"Unknown embedding_dimensions_mode in embedding configs: '{dimensions_mode}', fallback to 'auto'."
            )
            dimensions_mode = "auto"
        send_dimensions = dimensions_mode == "always"
        if dimensions_mode == "auto":
            api_base = _normalize_api_base(
                self.provider_config.get(
                    "embedding_api_base", "https://api.openai.com/v1"
                )
                or "https://api.openai.com/v1"
            )
            parsed_api_base = urlparse(api_base)
            model = (
                getattr(self, "model", None)
                or self.provider_config.get("embedding_model")
                or "text-embedding-3-small"
            )
            model_lower = str(model).lower()
            model_name = model_lower.rsplit("/", 1)[-1]
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
            except (ValueError, TypeError):
                logger.warning(
                    f"embedding_dimensions in embedding configs is not a valid integer: '{self.provider_config['embedding_dimensions']}', ignored."
                )
        return kwargs

    def get_dim(self) -> int:
        """获取向量的维度"""
        if "embedding_dimensions" in self.provider_config:
            try:
                return int(self.provider_config["embedding_dimensions"])
            except (ValueError, TypeError):
                logger.warning(
                    f"embedding_dimensions in embedding configs is not a valid integer: '{self.provider_config['embedding_dimensions']}', ignored."
                )
        return 0

    async def terminate(self):
        if self.client:
            await self.client.close()
