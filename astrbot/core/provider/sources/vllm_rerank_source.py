import aiohttp
from ..provider import RerankProvider
from ..register import register_provider_adapter
from ..entities import ProviderType, RerankResult


@register_provider_adapter(
    "vllm_rerank",
    "VLLM Rerank 适配器",
    provider_type=ProviderType.RERANK,
)
class VLLMRerankProvider(RerankProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.auth_key = provider_config.get("rerank_api_key", "")
        self.base_url = provider_config.get("rerank_api_base", "http://127.0.0.1:8000")
        self.base_url = self.base_url.rstrip("/")
        self.timeout = provider_config.get("timeout", 20)
        self.model = provider_config.get("rerank_model", "BAAI/bge-reranker-base")

        h = {}
        if self.auth_key:
            h["Authorization"] = f"Bearer {self.auth_key}"
        self.client = aiohttp.ClientSession(
            headers=h,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )

    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[RerankResult]:
        payload = {
            "query": query,
            "documents": documents,
            "model": self.model,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        async with self.client.post(
            f"{self.base_url}/v1/rerank", json=payload
        ) as response:
            response_data = await response.json()
            results = response_data.get("results", [])

            return [
                RerankResult(
                    index=result["index"],
                    relevance_score=result["relevance_score"],
                )
                for result in results
            ]

    async def terminate(self) -> None:
        """关闭客户端会话"""
        if self.client:
            await self.client.close()
            self.client = None
