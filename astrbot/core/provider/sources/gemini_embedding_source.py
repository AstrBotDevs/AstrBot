from google.genai import types
from google.genai.errors import APIError

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter
from .gemini_api_common import close_httpx_client, create_genai_async_client


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
        proxy = provider_config.get("proxy", "")

        self.client, self._http_client = create_genai_async_client(
            provider_label="Gemini Embedding",
            api_key=api_key,
            request_headers=self.request_headers,
            api_base=api_base,
            timeout=timeout,
            proxy=proxy,
        )

        self.model = provider_config.get(
            "embedding_model",
            "gemini-embedding-001",
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
            contents = [
                types.Content(parts=[types.Part.from_text(text=s)]) for s in text
            ]
            result = await self.client.models.embed_content(
                model=self.model,
                contents=contents,
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
        await close_httpx_client(
            getattr(self, "_http_client", None),
            label="Gemini Embedding",
        )
        self._http_client = None
