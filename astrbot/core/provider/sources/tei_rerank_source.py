import aiohttp

from astrbot import logger

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "tei_rerank",
    "HuggingFace TEI Rerank 适配器",
    provider_type=ProviderType.RERANK,
)
class TEIRerankProvider(RerankProvider):
    """HuggingFace Text Embeddings Inference (TEI) Rerank 适配器。"""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.api_key = provider_config.get("rerank_api_key", "")
        self.base_url = provider_config.get(
            "rerank_api_base", "http://127.0.0.1:8080"
        ).rstrip("/")
        self.timeout = provider_config.get("timeout", 20)
        self.truncate = provider_config.get("tei_rerank_truncate", False)
        self.truncation_direction = provider_config.get(
            "tei_rerank_truncation_direction", "right"
        ).lower()
        self.raw_scores = provider_config.get("tei_rerank_raw_scores", False)
        self.return_text = provider_config.get("tei_rerank_return_text", False)

        h = {}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
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
        if not self.client or self.client.closed:
            logger.error("[TEI Rerank] Client session is not initialized or closed")
            return []
        if not documents:
            logger.warning(
                "[TEI Rerank] Document list is empty, returning empty results"
            )
            return []
        if not query.strip():
            logger.warning("[TEI Rerank] Query is empty, returning empty results")
            return []
        payload: dict = {
            "query": query,
            "texts": documents,
        }

        if self.truncate:
            payload["truncate"] = True
            payload["truncation_direction"] = self.truncation_direction
        if self.raw_scores:
            payload["raw_scores"] = True
        if self.return_text:
            payload["return_text"] = True

        try:
            rerank_url = f"{self.base_url}/rerank"
            logger.debug(
                f"[TEI Rerank] Request: query='{query[:50]}...', "
                f"doc_count={len(documents)}"
            )
            async with self.client.post(rerank_url, json=payload) as response:
                if response.status != 200:
                    try:
                        error_data = await response.json()
                        error_msg = error_data.get(
                            "error", error_data.get("message", "Unknown error")
                        )
                    except Exception:
                        error_msg = await response.text()
                    logger.error(
                        f"[TEI Rerank] API returned HTTP {response.status}: {error_msg}"
                    )
                    raise Exception(f"TEI Rerank HTTP {response.status}: {error_msg}")

                response_data = await response.json()

                if not response_data:
                    logger.warning(
                        f"[TEI Rerank] API returned empty results. "
                        f"Response: {response_data}"
                    )
                    return []

                results = []
                for rank_item in response_data:
                    results.append(
                        RerankResult(
                            index=rank_item["index"],
                            relevance_score=rank_item["score"],
                        )
                    )

                if top_n is not None and top_n > 0:
                    results = results[:top_n]

                logger.debug(
                    f"[TEI Rerank] Successfully returned {len(results)} results"
                )
                return results

        except aiohttp.ClientError as e:
            logger.error(f"[TEI Rerank] Network error: {e}")
            raise Exception(f"TEI Rerank network error: {e}") from e
        except Exception as e:
            logger.error(f"[TEI Rerank] Error: {e}")
            raise

    async def test(self) -> None:
        if not self.client or self.client.closed:
            raise Exception("TEI Rerank client session is not initialized")

        health_url = f"{self.base_url}/health"
        try:
            async with self.client.get(health_url) as response:
                if response.status != 200:
                    raise Exception(
                        f"TEI service health check failed at {self.base_url}: "
                        f"HTTP {response.status}"
                    )
        except aiohttp.ClientError as e:
            raise Exception(
                f"TEI service is not reachable at {self.base_url}: {e}"
            ) from e
        result = await self.rerank("Apple", documents=["apple", "banana"])
        if not result:
            raise Exception(
                "TEI Rerank provider test failed: no results returned. "
                "Please ensure a reranker model is loaded in TEI."
            )

    async def terminate(self) -> None:
        if self.client and not self.client.closed:
            await self.client.close()
            self.client = None
