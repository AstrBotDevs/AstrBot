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
        http_client = None
        if proxy:
            logger.info(f"[OpenAI Embedding] 使用代理: {proxy}")
            http_client = httpx.AsyncClient(proxy=proxy)
        api_base = provider_config.get("embedding_api_base", "").strip()
        if not api_base:
            api_base = "https://api.openai.com/v1"
        else:
            api_base = api_base.removesuffix("/")
            if not api_base.endswith("/v1"):
                api_base = f"{api_base}/v1"
        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=api_base,
            timeout=int(provider_config.get("timeout", 20)),
            http_client=http_client,
        )
        self.model = provider_config.get("embedding_model", "text-embedding-3-small")

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入"""
        embedding = await self.client.embeddings.create(
            input=text,
            model=self.model,
            dimensions=self.get_dim(),
        )
        return embedding.data[0].embedding

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入"""
        embeddings = await self.client.embeddings.create(
            input=text,
            model=self.model,
            dimensions=self.get_dim(),
        )
        return [item.embedding for item in embeddings.data]

    async def detect_dim(self) -> int:
        """探测模型可用的最大向量维度"""

        async def _request_dim(dimensions: int | None) -> int:
            kwargs = {
                "input": "echo",
                "model": self.model,
            }
            if dimensions is not None:
                kwargs["dimensions"] = dimensions
            embedding = await self.client.embeddings.create(**kwargs)
            return len(embedding.data[0].embedding)

        # 1) 默认调用，获取当前默认维度
        base_dim = await _request_dim(None)

        # 2) 先判断 dimensions 参数是否可调
        probe_dim = base_dim + 1
        try:
            probe_result = await _request_dim(probe_dim)
            if probe_result != probe_dim:
                return base_dim
        except Exception:
            return base_dim

        # 3) 可调时探测上界：指数扩张 + 二分
        max_cap = 32768
        low = probe_dim
        high = max(base_dim * 2, probe_dim + 1)
        if high > max_cap:
            high = max_cap

        while high < max_cap:
            try:
                result_dim = await _request_dim(high)
                if result_dim != high:
                    break
                low = high
                high = min(high * 2, max_cap)
            except Exception:
                break

        left = low + 1
        right = high - 1
        while left <= right:
            mid = (left + right) // 2
            try:
                result_dim = await _request_dim(mid)
                if result_dim == mid:
                    low = mid
                    left = mid + 1
                else:
                    right = mid - 1
            except Exception:
                right = mid - 1

        return low

    def get_dim(self) -> int:
        """获取向量的维度"""
        return int(self.provider_config.get("embedding_dimensions", 1024))

    async def terminate(self):
        if self.client:
            await self.client.close()
