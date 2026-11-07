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
    # gemini-embedding-2 dropped task_type support; the task must be passed
    # as a text prefix instead. See https://ai.google.dev/gemini-api/docs/embeddings
    EMBEDDING_V2_MODEL_PREFIX = "gemini-embedding-2"
    V2_QUERY_PREFIX = "task: search result | query: "
    V2_DOCUMENT_FORMAT = "title: none | text: {text}"

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

        api_key: str = provider_config["embedding_api_key"]
        api_base: str = provider_config["embedding_api_base"]
        timeout: int = int(provider_config.get("timeout", 20))

        http_options = types.HttpOptions(
            timeout=timeout * 1000, headers=self.request_headers
        )
        if api_base:
            api_base = api_base.removesuffix("/")
            http_options.base_url = api_base
        proxy = provider_config.get("proxy", "")
        if proxy:
            http_options.async_client_args = {"proxy": proxy}
            logger.info(f"[Gemini Embedding] 使用代理: {proxy}")

        self.client = genai.Client(api_key=api_key, http_options=http_options).aio
        # The SDK adds its own lower-case UA alongside our explicit header.
        self.client._api_client._http_options.headers.pop("user-agent", None)

        self.model = provider_config.get(
            "embedding_model",
            "gemini-embedding-001",
        )

    async def _embed(
        self, texts: list[str], task_type: str | None = None
    ) -> list[list[float]]:
        """Embed texts, optionally applying a retrieval task type.

        Args:
            texts: The texts to embed.
            task_type: Gemini task_type (e.g. RETRIEVAL_QUERY). Only supported
                by the gemini-embedding-001 family, ignored when None.

        Returns:
            The embedding vectors, in input order.

        Raises:
            Exception: When the Gemini API request fails.
        """
        try:
            contents = [
                types.Content(parts=[types.Part.from_text(text=s)]) for s in texts
            ]
            config_kwargs: dict = {"output_dimensionality": self.get_dim()}
            if task_type:
                config_kwargs["task_type"] = task_type
            result = await self.client.models.embed_content(
                model=self.model,
                contents=contents,
                config=types.EmbedContentConfig(**config_kwargs),
            )
            assert result.embeddings is not None

            embeddings: list[list[float]] = []
            for embedding in result.embeddings:
                assert embedding.values is not None
                embeddings.append(embedding.values)
            return embeddings
        except APIError as e:
            raise Exception(f"Gemini Embedding API请求失败: {e.message}")

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入"""
        return (await self._embed([text]))[0]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入"""
        return await self._embed(text)

    async def get_query_embedding(self, text: str) -> list[float]:
        """Get the embedding for a retrieval query.

        gemini-embedding-001 gets the RETRIEVAL_QUERY task type;
        gemini-embedding-2 (no task_type support) gets the retrieval task
        prefix in the text itself.

        Args:
            text: The query text.

        Returns:
            The query embedding vector.
        """
        if self.model.startswith(self.EMBEDDING_V2_MODEL_PREFIX):
            return (await self._embed([self.V2_QUERY_PREFIX + text]))[0]
        return (await self._embed([text], task_type="RETRIEVAL_QUERY"))[0]

    async def get_document_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for documents to be indexed for retrieval.

        gemini-embedding-001 gets the RETRIEVAL_DOCUMENT task type;
        gemini-embedding-2 gets the document structure prefix in the text
        itself. AstrBot has no per-document title, so ``title: none`` is used
        as documented.

        Args:
            texts: The document texts to index.

        Returns:
            The document embedding vectors, in input order.
        """
        if self.model.startswith(self.EMBEDDING_V2_MODEL_PREFIX):
            texts = [self.V2_DOCUMENT_FORMAT.format(text=s) for s in texts]
            return await self._embed(texts)
        return await self._embed(texts, task_type="RETRIEVAL_DOCUMENT")

    def get_dim(self) -> int:
        """获取向量的维度"""
        return int(self.provider_config.get("embedding_dimensions", 768))

    async def terminate(self):
        if self.client:
            await self.client.aclose()
