import aiohttp

from astrbot import logger

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "nvidia_rerank", "NVIDIA Rerank 适配器", provider_type=ProviderType.RERANK
)
class NvidiaRerankProvider(RerankProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("nvidia_rerank_api_key", "")
        self.base_url = provider_config.get(
            "nvidia_rerank_api_base", "https://ai.api.nvidia.com/v1/retrieval"
        ).rstrip("/")
        self.timeout = provider_config.get("timeout", 20)
        self.model = provider_config.get(
            "nvidia_rerank_model", "nv-rerank-qa-mistral-4b:1"
        )
        self.model_endpoint = provider_config.get(
            "nvidia_rerank_model_endpoint", "/reranking"
        )
        self.truncate = provider_config.get("nvidia_rerank_truncate", "")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        self.client = aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=self.timeout)
        )

        self.set_model(self.model)

    def _get_endpoint(self) -> str:
        """
        构建完整API URL。

        根据 Nvidia Rerank API 文档来看，当前URL存在不同模型格式不一致的问题。
        这里针对模型名做一个基础判断用以适配，后续要等Nvidia统一API格式后再做调整。

        例：
        模型： nv-rerank-qa-mistral-4b:1
        URL: .../v1/retrieval/nvidia/reranking

        模型： nvidia/llama-nemotron-rerank-1b-v2
        URL: .../v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking
        """

        model_path = "nvidia"
        logger.debug(f"[NVIDIA Rerank] Building endpoint for model: {self.model}")
        if "/" in self.model:
            model_path = self.model.strip("/")
        endpoint = self.model_endpoint.lstrip("/")
        return f"{self.base_url}/{model_path}/{endpoint}"

    def _build_payload(self, query: str, documents: list[str]) -> dict:
        """构建请求载荷"""
        payload = {
            "model": self.model,
            "query": {"text": query},
            "passages": [{"text": doc} for doc in documents],
        }
        if self.truncate:
            payload["truncate"] = self.truncate
        return payload

    def _parse_results(
        self, response_data: dict, top_n: int | None
    ) -> list[RerankResult]:
        """解析响应数据"""
        results = response_data.get("rankings", [])
        if not results:
            logger.warning(f"[NVIDIA Rerank] Empty response: {response_data}")
            return []

        rerank_results = []
        for idx, item in enumerate(results):
            try:
                index = item.get("index", idx)
                score = item.get("relevance_score", item.get("logit", 0.0))
                rerank_results.append(
                    RerankResult(index=index, relevance_score=float(score))
                )
            except Exception as e:
                logger.warning(
                    f"[NVIDIA Rerank] Result parsing error: {e}, Data={item}"
                )

        rerank_results.sort(key=lambda x: x.relevance_score, reverse=True)

        if top_n is not None and top_n > 0:
            return rerank_results[:top_n]
        return rerank_results

    def _log_usage(self, data: dict) -> None:
        usage = data.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)
        if total_tokens > 0:
            logger.debug(f"[NVIDIA Rerank] Token Usage: {total_tokens}")

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        if not self.client or self.client.closed:
            logger.error("[NVIDIA Rerank] Client session not initialized or closed")
            return []

        if not documents or not query.strip():
            logger.warning(
                "[NVIDIA Rerank] Input data is invalid, query or documents are empty"
            )
            return []

        try:
            payload = self._build_payload(query, documents)
            request_url = self._get_endpoint()

            async with self.client.post(request_url, json=payload) as response:
                response_data = await response.json()
                logger.debug(f"[NVIDIA Rerank] API Response: {response_data}")

                if response.status != 200:
                    error_detail = response_data.get(
                        "detail", response_data.get("message", "Unknown Error")
                    )
                    raise Exception(f"HTTP {response.status} - {error_detail}")

                results = self._parse_results(response_data, top_n)
                self._log_usage(response_data)
                return results

        except aiohttp.ClientError as e:
            logger.error(f"[NVIDIA Rerank] Network error: {e}")
            raise Exception(f"Network error: {e}") from e
        except Exception as e:
            logger.error(f"[NVIDIA Rerank] Error: {e}")
            raise Exception(f"Rerank error: {e}") from e

    async def terminate(self) -> None:
        if self.client and not self.client.closed:
            await self.client.close()
            self.client = None
