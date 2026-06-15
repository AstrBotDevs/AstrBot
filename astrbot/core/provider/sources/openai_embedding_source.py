import re

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
        """构建嵌入请求的可选参数"""
        kwargs = {}
        if "embedding_dimensions" in self.provider_config:
            dim_setting = self.provider_config["embedding_dimensions"]
            if dim_setting is not None and str(dim_setting).strip() != "":
                try:
                    dim_val = int(dim_setting)
                    # 只有明确指定维度且大于0时才携带参数。
                    if dim_val > 0:
                        kwargs["dimensions"] = dim_val
                    else:
                        # 留空或填 0 隐式丢弃此参数，用于规避 SiliconFlow、vLLM 等严格校验平台报 HTTP 400
                        logger.debug(
                            f"embedding_dimensions '{dim_val}' is <= 0, omitted to ensure compatibility with strict providers."
                        )
                except (ValueError, TypeError):
                    logger.warning(
                        f"embedding_dimensions in embedding configs is not a valid integer: '{dim_setting}', ignored."
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
