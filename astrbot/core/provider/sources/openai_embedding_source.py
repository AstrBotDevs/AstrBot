import httpx
from openai import AsyncOpenAI

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


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
        self._http_client = None
        if proxy:
            logger.info(f"[OpenAI Embedding] {provider_id} Using proxy: {proxy}")
            self._http_client = httpx.AsyncClient(proxy=proxy)
        # 处理 API base URL：带路径的地址保持原样，纯域名自动补 /v1
        from urllib.parse import urlsplit

        api_base = (
            provider_config.get("embedding_api_base", "https://api.openai.com/v1")
            .strip()
            .removesuffix("/")
            .removesuffix("/embeddings")
        )
        if api_base:
            parsed = urlsplit(api_base)
            # 无 scheme 时 urlsplit 会把 host 当 path，需要补上 scheme
            if not parsed.scheme:
                api_base = f"https://{api_base}"
                parsed = urlsplit(api_base)
            # 只在纯域名（无路径或只有 /）时追加 /v1，带路径的地址保持原样
            # 这样智谱 /api/paas/v4、火山 /api/v3 等不会被破坏
            if not parsed.path or parsed.path == "/":
                api_base = f"{api_base}/v1"
        logger.info(f"[OpenAI Embedding] {provider_id} Using API Base: {api_base}")
        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=api_base,
            timeout=int(provider_config.get("timeout", 20)),
            http_client=self._http_client,
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
        if self._http_client:
            await self._http_client.aclose()
