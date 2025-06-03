from google import genai
from google.genai import types
from google.genai.errors import APIError
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter
from ..entities import ProviderType


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

        api_key: str = provider_config.get("embedding_api_key")
        api_base: str = provider_config.get("embedding_api_base", None)
        timeout: int = int(provider_config.get("timeout", 20))

        http_options = types.HttpOptions(timeout=timeout * 1000)
        if api_base:
            if api_base.endswith("/"):
                api_base = api_base[:-1]
            http_options.base_url = api_base

        self.client = genai.Client(api_key=api_key, http_options=http_options).aio

        self.model = provider_config.get(
            "embedding_model", "gemini-embedding-exp-03-07"
        )
        self.dimension = provider_config.get("embedding_dimensions", 768)

    async def get_embedding(self, text: str) -> list[float]:
        """
        获取文本的嵌入
        """
        try:
            result = await self.client.models.embed_content(
                model=self.model, contents=text
            )
            return result.embeddings[0].values
        except APIError as e:
            raise Exception(f"Gemini Embedding API请求失败: {e.message}")

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        批量获取文本的嵌入
        """
        try:
            result = await self.client.models.embed_content(
                model=self.model, contents=texts
            )
            return [embedding.values for embedding in result.embeddings]
        except APIError as e:
            raise Exception(f"Gemini Embedding API批量请求失败: {e.message}")

    def get_dim(self) -> int:
        """获取向量的维度"""
        return self.dimension
