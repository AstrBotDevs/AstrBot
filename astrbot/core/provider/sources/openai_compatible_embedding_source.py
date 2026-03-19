from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


def normalize_openai_compatible_embedding_api_base(api_base: str) -> str:
    """Normalize API base while preserving provider-specific path prefixes.

    Handles URLs with or without scheme:
    - Empty/whitespace → https://api.openai.com/v1
    - Host only (api.openai.com) → https://api.openai.com/v1
    - Full URL with path (https://example.com/api/v3) → preserved as-is
    """
    cleaned_api_base = api_base.strip().removesuffix("/")
    if not cleaned_api_base:
        return "https://api.openai.com/v1"

    parsed_api_base = urlsplit(cleaned_api_base)
    # If no scheme, the URL is parsed incorrectly (host becomes path)
    if not parsed_api_base.scheme:
        cleaned_api_base = f"https://{cleaned_api_base}"
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
    """Read the explicit bool switch used by OpenAI-compatible presets."""
    raw_value = provider_config.get("send_dimensions_param", False)
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value not in (None, ""):
        logger.warning(
            "send_dimensions_param should be a boolean in embedding configs: '%s', treated as disabled.",
            raw_value,
        )
    return False


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
        self._http_client = None

        proxy = provider_config.get("proxy", "")
        if proxy:
            logger.info(f"[OpenAI Compatible Embedding] 使用代理: {proxy}")
            self._http_client = httpx.AsyncClient(proxy=proxy)

        try:
            timeout = int(provider_config.get("timeout", 20))
        except (ValueError, TypeError):
            logger.warning(
                "Invalid timeout value in provider config: '%s'. Using default 20s.",
                provider_config.get("timeout"),
            )
            timeout = 20

        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=normalize_openai_compatible_embedding_api_base(
                provider_config.get("embedding_api_base", "")
            ),
            timeout=timeout,
            http_client=self._http_client,
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
        if self._http_client:
            await self._http_client.aclose()
