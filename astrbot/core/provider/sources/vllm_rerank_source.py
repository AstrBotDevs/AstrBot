import asyncio
from collections.abc import Mapping

import aiohttp

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter

_REQUEST_ERROR = "VLLM rerank request failed"


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
        self.api_suffix = provider_config.get("rerank_api_suffix", "/v1/rerank")
        if self.api_suffix is None:
            self.api_suffix = "/v1/rerank"
        if self.api_suffix and not self.api_suffix.startswith("/"):
            self.api_suffix = "/" + self.api_suffix
        self.timeout = provider_config.get("timeout", 20)
        self.model = provider_config.get("rerank_model", "BAAI/bge-reranker-base")

        h = {}
        if self.auth_key:
            h["Authorization"] = f"Bearer {self.auth_key}"
        self.client = aiohttp.ClientSession(
            headers=h,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )

    def _parse_results(self, response_data: object) -> list[RerankResult]:
        if not isinstance(response_data, Mapping):
            raise ValueError("VLLM rerank returned an invalid response")

        results = response_data.get("results")
        if not isinstance(results, list) or not results:
            raise ValueError("VLLM rerank returned invalid result data")

        rerank_results: list[RerankResult] = []
        for result in results:
            try:
                if not isinstance(result, Mapping):
                    raise TypeError("rerank result must be an object")
                rerank_results.append(
                    RerankResult(
                        index=int(result["index"]),
                        relevance_score=float(result["relevance_score"]),
                    )
                )
            except Exception as exc:
                logger.warning(
                    "VLLM rerank result parsing failed: %s", safe_error("", exc)
                )

        if not rerank_results:
            raise ValueError("VLLM rerank returned no valid results")
        return rerank_results

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        if not documents:
            return []
        payload = {
            "query": query,
            "documents": documents,
            "model": self.model,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        client = self.client
        if client is None or getattr(client, "closed", False):
            logger.error("VLLM rerank client is not available")
            return []

        rerank_url = f"{self.base_url}{self.api_suffix}"
        try:
            async with client.post(
                rerank_url,
                json=payload,
            ) as response:
                status = getattr(response, "status", 200)
                if not isinstance(status, int):
                    logger.error("VLLM rerank HTTP request returned an invalid status")
                    raise RuntimeError(_REQUEST_ERROR)
                if not 200 <= status < 300:
                    logger.error(
                        "VLLM rerank HTTP request failed with status %d", status
                    )
                    raise RuntimeError(_REQUEST_ERROR)

                response_data = await response.json()
                return self._parse_results(response_data)
        except asyncio.CancelledError:
            raise
        except aiohttp.ClientError as exc:
            logger.error("VLLM rerank network failure: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None
        except Exception as exc:
            logger.error("VLLM rerank request failed: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None

    async def terminate(self) -> None:
        """关闭客户端会话"""
        client = self.client
        self.client = None
        if client is None or getattr(client, "closed", False):
            return
        try:
            await client.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("VLLM rerank client close failed: %s", safe_error("", exc))
