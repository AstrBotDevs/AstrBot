from urllib.parse import urlsplit

import aiohttp

from astrbot import logger

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "vllm_rerank",
    "VLLM Rerank 适配器",
    provider_type=ProviderType.RERANK,
)
class VLLMRerankProvider(RerankProvider):
    @staticmethod
    def _resolve_rerank_endpoint(base_url: str) -> str:
        normalized = base_url.strip().removesuffix("/")
        if normalized.endswith("/rerank"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/rerank"

        has_scheme = "://" in normalized
        parsed = urlsplit(normalized if has_scheme else f"//{normalized}")
        if not has_scheme:
            if parsed.path not in ("", "/"):
                raise ValueError(
                    "VLLM Rerank API Base URL must include a scheme when a path is provided: "
                    f"{base_url!r}"
                )
            normalized = f"http://{normalized}"
            parsed = urlsplit(normalized)

        if not parsed.path or parsed.path == "/":
            return f"{normalized}/v1/rerank"
        return normalized

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.auth_key = provider_config.get("rerank_api_key", "")
        self.base_url = provider_config.get("rerank_api_base", "http://127.0.0.1:8000")
        self.base_url = self.base_url.rstrip("/")
        self.endpoint_url = self._resolve_rerank_endpoint(self.base_url)
        self.timeout = provider_config.get("timeout", 20)
        self.model = provider_config.get("rerank_model", "BAAI/bge-reranker-base")

        h = {}
        if self.auth_key:
            h["Authorization"] = f"Bearer {self.auth_key}"
        logger.info(f"[vLLM Rerank] Using API URL: {self.endpoint_url}")
        self.client = aiohttp.ClientSession(
            headers=h,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        payload = {
            "query": query,
            "documents": documents,
            "model": self.model,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        assert self.client is not None
        async with self.client.post(
            self.endpoint_url,
            json=payload,
        ) as response:
            response_data = await response.json()
            if isinstance(response_data, dict) and "error" in response_data:
                error = response_data["error"]
                if isinstance(error, dict):
                    code = error.get("code", "unknown")
                    message = error.get("message", "Unknown rerank API error")
                    raise ValueError(f"Rerank API error {code}: {message}")
                raise ValueError(f"Rerank API error: {error}")
            response.raise_for_status()
            if not isinstance(response_data, dict):
                raise ValueError(
                    "Unexpected rerank API response format: "
                    f"{type(response_data).__name__}"
                )
            results = response_data.get("results", [])

            if not results:
                logger.warning(
                    f"Rerank API 返回了空的列表数据。原始响应: {response_data}",
                )

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
