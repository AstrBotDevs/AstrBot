from openai import AsyncOpenAI
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter
from ..entities import ProviderType


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
        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=provider_config.get(
                "embedding_api_base", "https://api.openai.com/v1"
            ),
            timeout=int(provider_config.get("timeout", 20)),
        )
        self.model = provider_config.get("embedding_model", "text-embedding-3-small")
        self.dimension = provider_config.get("embedding_dimensions", 1024)

    async def get_embedding(self, text: str) -> list[float]:
        """
        获取文本的嵌入
        """
        embedding = await self.client.embeddings.create(input=text, model=self.model)
        return embedding.data[0].embedding

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        批量获取文本的嵌入
        """
        embeddings = await self.client.embeddings.create(input=texts, model=self.model)
        return [item.embedding for item in embeddings.data]

    def get_dim(self) -> int:
        """获取向量的维度"""
        return self.dimension
