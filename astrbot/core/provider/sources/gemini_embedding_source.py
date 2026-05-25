from typing import cast

from google import genai
from google.genai import types
from google.genai.errors import APIError

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


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
        proxy = provider_config.get("proxy", "")
        if proxy:
            http_options.async_client_args = {"proxy": proxy}
            logger.info(f"[Gemini Embedding] 使用代理: {proxy}")

        self.client = genai.Client(api_key=api_key, http_options=http_options).aio

        self.model = provider_config.get(
            "embedding_model",
            "gemini-embedding-exp-03-07",
        )

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入"""
        try:
            result = await self.client.models.embed_content(
                model=self.model,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.get_dim(),
                ),
            )
            assert result.embeddings is not None
            assert result.embeddings[0].values is not None
            return result.embeddings[0].values
        except APIError as e:
            raise Exception(f"Gemini Embedding API请求失败: {e.message}")

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入"""
        try:
            result = await self.client.models.embed_content(
                model=self.model,
                contents=cast(types.ContentListUnion, text),
                config=types.EmbedContentConfig(
                    output_dimensionality=self.get_dim(),
                ),
            )
            assert result.embeddings is not None

            embeddings: list[list[float]] = []
            for embedding in result.embeddings:
                assert embedding.values is not None
                embeddings.append(embedding.values)
            return embeddings
        except APIError as e:
            raise Exception(f"Gemini Embedding API批量请求失败: {e.message}")

    def get_dim(self) -> int:
        """获取向量的维度"""
        return int(self.provider_config.get("embedding_dimensions", 768))

    async def terminate(self):
        if self.client:
            await self.client.aclose()
