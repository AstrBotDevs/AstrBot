import asyncio

import aiohttp

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter

_REQUEST_ERROR = "NVIDIA rerank request failed"


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
            "nvidia_rerank_model", "nvidia/llama-nemotron-rerank-vl-1b-v2"
        )
        self.model_endpoint = provider_config.get(
            "nvidia_rerank_model_endpoint", "/reranking"
        )
        self.truncate = provider_config.get("nvidia_rerank_truncate", "")

        self.client = None
        self.set_model(self.model)

    async def _get_client(self):
        if self.client is None or self.client.closed:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            self.client = aiohttp.ClientSession(
                headers=headers, timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self.client

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
        logger.debug("[NVIDIA Rerank] Building endpoint")
        if "/" in self.model:
            """遵循NVIDIA API的URL规则，替换模型名中特殊字符"""
            model_path = self.model.strip("/").replace(".", "_")
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
            logger.warning("[NVIDIA Rerank] Empty response")
            return []

        if not isinstance(results, list):
            logger.warning("[NVIDIA Rerank] Invalid rankings response")
            return []

        rerank_results = []
        for idx, item in enumerate(results):
            try:
                if not isinstance(item, dict):
                    raise TypeError("ranking item must be an object")
                index = item.get("index", idx)
                score = item.get("relevance_score", item.get("logit", 0.0))
                rerank_results.append(
                    RerankResult(index=index, relevance_score=float(score))
                )
            except Exception as exc:
                logger.warning(
                    "[NVIDIA Rerank] Result parsing failed: %s",
                    safe_error("", exc),
                )

        rerank_results.sort(key=lambda x: x.relevance_score, reverse=True)

        if top_n is not None and top_n > 0:
            return rerank_results[:top_n]
        return rerank_results

    def _log_usage(self, data: dict) -> None:
        usage = data.get("usage", {})
        if not isinstance(usage, dict):
            logger.warning("[NVIDIA Rerank] Invalid usage metadata")
            return
        total_tokens = usage.get("total_tokens", 0)
        try:
            token_count = int(total_tokens)
        except TypeError, ValueError:
            logger.warning("[NVIDIA Rerank] Invalid token usage metadata")
            return
        if token_count > 0:
            logger.debug("[NVIDIA Rerank] Token Usage: %d", token_count)

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        client = await self._get_client()
        if not client or client.closed:
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

            async with client.post(request_url, json=payload) as response:
                if response.status != 200:
                    try:
                        response_data = await response.json()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning(
                            "[NVIDIA Rerank] Failed to parse error response: %s",
                            safe_error("", exc),
                        )
                        response_data = "<unavailable>"

                    logger.error(
                        "[NVIDIA Rerank] API request failed with status %s: %s",
                        response.status,
                        safe_error("", str(response_data)),
                    )
                    raise RuntimeError(_REQUEST_ERROR)

                response_data = await response.json()
                logger.debug("[NVIDIA Rerank] API response received")
                results = self._parse_results(response_data, top_n)
                self._log_usage(response_data)
                return results

        except asyncio.CancelledError:
            raise
        except aiohttp.ClientError as exc:
            logger.error("[NVIDIA Rerank] Network failure: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None
        except Exception as exc:
            logger.error("[NVIDIA Rerank] Request failed: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None

    async def terminate(self) -> None:
        client = self.client
        self.client = None
        if client is None or client.closed:
            return
        try:
            await client.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "[NVIDIA Rerank] Client close failed: %s", safe_error("", exc)
            )
