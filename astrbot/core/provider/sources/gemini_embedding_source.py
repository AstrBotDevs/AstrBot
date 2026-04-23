from typing import Any, cast

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

    async def get_models(self) -> list[str]:
        try:
            models = await self.client.models.list()
            all_model_ids: list[str] = []
            embedding_model_ids: list[str] = []

            for model in getattr(models, "page", []):
                model_id = self._extract_model_id(model)
                if not model_id:
                    continue
                all_model_ids.append(model_id)
                if self._supports_embedding(model, model_id):
                    embedding_model_ids.append(model_id)

            all_model_ids = sorted(dict.fromkeys(all_model_ids))
            embedding_model_ids = sorted(dict.fromkeys(embedding_model_ids))

            return embedding_model_ids or all_model_ids
        except Exception as e:
            raise Exception(f"获取 Gemini 嵌入模型列表失败: {e!s}") from e

    def get_dim(self) -> int:
        """获取向量的维度"""
        return int(self.provider_config.get("embedding_dimensions", 768))

    async def terminate(self):
        if self.client:
            await self.client.aclose()

    @staticmethod
    def _extract_model_id(model: Any) -> str:
        model_name = getattr(model, "name", "") or getattr(model, "model", "")
        if not model_name:
            return ""
        return str(model_name).removeprefix("models/")

    @classmethod
    def _supports_embedding(cls, model: Any, model_id: str) -> bool:
        supported_actions = getattr(model, "supported_actions", None) or getattr(
            model, "supported_generation_methods", []
        )
        if isinstance(supported_actions, list):
            normalized_actions = {
                str(action).lower().replace("_", "").replace("-", "")
                for action in supported_actions
            }
            if "embedcontent" in normalized_actions:
                return True

        return cls._looks_like_embedding_model(model_id)

    @staticmethod
    def _looks_like_embedding_model(model_id: str) -> bool:
        normalized_model_id = model_id.lower()
        return "embedding" in normalized_model_id or "embed" in normalized_model_id
