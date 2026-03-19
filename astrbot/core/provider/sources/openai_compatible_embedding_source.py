from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


def normalize_openai_compatible_embedding_api_base(api_base: str) -> str:
    """Normalize API base while preserving provider-specific path prefixes."""
    cleaned_api_base = api_base.strip().removesuffix("/")
    if not cleaned_api_base:
        return "https://api.openai.com/v1"

    parsed_api_base = urlsplit(cleaned_api_base)
    if parsed_api_base.path and parsed_api_base.path != "/":
        return cleaned_api_base

    return f"{cleaned_api_base}/v1"


def parse_embedding_dimensions(provider_config: dict) -> int:
    """Return the configured local vector size, or 0 when unset/invalid."""
    raw_dimensions = provider_config.get("embedding_dimensions")
    if raw_dimensions in (None, ""):
        return 0

    try:
        return int(raw_dimensions)
    except (ValueError, TypeError):
        logger.warning(
            "embedding_dimensions in embedding configs is not a valid integer: '%s', ignored.",
            raw_dimensions,
        )
        return 0


def should_send_dimensions_param(provider_config: dict) -> bool:
    """Keep dimensions opt-in for generic OpenAI-compatible services."""
    raw_value = provider_config.get("send_dimensions_param", False)
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw_value)


@register_provider_adapter(
    "openai_compatible_embedding",
    "OpenAI Compatible Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        proxy = provider_config.get("proxy", "")
        http_client = None
        if proxy:
            logger.info(f"[OpenAI Compatible Embedding] 使用代理: {proxy}")
            http_client = httpx.AsyncClient(proxy=proxy)

        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=normalize_openai_compatible_embedding_api_base(
                provider_config.get("embedding_api_base", "")
            ),
            timeout=int(provider_config.get("timeout", 20)),
            http_client=http_client,
        )
        self.model = provider_config.get("embedding_model", "text-embedding-3-small")

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入。"""
        kwargs = self._embedding_kwargs()
        embedding = await self.client.embeddings.create(
            input=text,
            model=self.model,
            **kwargs,
        )
        return embedding.data[0].embedding

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入。"""
        kwargs = self._embedding_kwargs()
        embeddings = await self.client.embeddings.create(
            input=text,
            model=self.model,
            **kwargs,
        )
        return [item.embedding for item in embeddings.data]

    def _embedding_kwargs(self) -> dict:
        """Only send optional parameters the upstream explicitly needs."""
        dimensions = parse_embedding_dimensions(self.provider_config)
        if should_send_dimensions_param(self.provider_config) and dimensions > 0:
            return {"dimensions": dimensions}
        return {}

    def get_dim(self) -> int:
        """获取向量的维度。"""
        return parse_embedding_dimensions(self.provider_config)

    async def terminate(self):
        if self.client:
            await self.client.close()
