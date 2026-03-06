from collections.abc import Mapping
from typing import Any

import aiohttp

from astrbot import logger

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "openai_rerank",
    "通用 Rerank 适配器",
    provider_type=ProviderType.RERANK,
    default_config_tmpl={
        "rerank_api_key": "",
        "rerank_api_url": "https://api.example.com/v1/rerank",
        "rerank_model": "",
        "timeout": 30,
    },
    provider_display_name="通用 Rerank",
)
class OpenAIRerankProvider(RerankProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)

        self.api_key = str(provider_config.get("rerank_api_key", "")).strip()
        self.api_url = str(
            provider_config.get("rerank_api_url")
            or provider_config.get("rerank_api_base", "")
        ).strip()
        self.model = str(provider_config.get("rerank_model", "")).strip()
        self.timeout = int(provider_config.get("timeout", 30))

        if not self.api_url:
            raise ValueError("通用 Rerank API URL 不能为空。")
        if not self.api_key:
            raise ValueError("通用 Rerank API Key 不能为空。")

        self.client = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )

        self.set_model(self.model)
        logger.info(f"AstrBot 通用 Rerank 初始化完成。API URL: {self.api_url}")

    @staticmethod
    def _normalize_documents(documents: list[Any]) -> list[str | dict[str, Any]]:
        normalized_documents: list[str | dict[str, Any]] = []
        for index, document in enumerate(documents):
            if isinstance(document, str):
                normalized_documents.append(document)
                continue
            if isinstance(document, Mapping):
                normalized_documents.append(dict(document))
                continue
            raise TypeError(
                f"documents[{index}] 必须是字符串或对象，当前类型为 {type(document).__name__}。"
            )

        return normalized_documents

    def _build_payload(
        self,
        query: str,
        documents: list[str | dict[str, Any]],
        top_n: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": query,
            "documents": documents,
        }

        if self.model:
            payload["model"] = self.model

        if top_n is not None:
            if top_n <= 0:
                raise ValueError("top_n 必须大于 0。")
            top_k = min(top_n, 100)
            if top_k != top_n:
                logger.warning(
                    f"通用 Rerank top_n={top_n} 超出接口限制，已截断为 {top_k}。"
                )
            payload["top_k"] = top_k

        return payload

    @staticmethod
    def _parse_results(response_data: Any) -> list[RerankResult]:
        if not isinstance(response_data, dict):
            raise ValueError("通用 Rerank 返回格式错误，响应不是 JSON 对象。")

        results = response_data.get("results", [])
        if not isinstance(results, list):
            logger.warning(f"通用 Rerank 返回异常 results 字段: {response_data}")
            return []

        parsed_results: list[RerankResult] = []
        for idx, result in enumerate(results):
            if not isinstance(result, dict):
                logger.warning(f"通用 Rerank 第 {idx} 个结果格式异常: {result}")
                continue

            try:
                result_index = int(result.get("index", idx))
                relevance_score = float(
                    result.get("relevance_score", result.get("score", 0.0))
                )
            except (TypeError, ValueError) as exc:
                logger.warning(
                    f"通用 Rerank 第 {idx} 个结果缺少有效 index 或 score: {result}"
                )
                logger.debug("通用 Rerank 结果解析失败", exc_info=exc)
                continue

            parsed_results.append(
                RerankResult(
                    index=result_index,
                    relevance_score=relevance_score,
                )
            )

        if not parsed_results:
            logger.warning(f"通用 Rerank 返回空结果: {response_data}")

        return parsed_results

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        if not documents:
            return []
        if not query.strip():
            logger.warning("通用 Rerank 查询文本为空，返回空结果。")
            return []
        if not self.client:
            logger.error("通用 Rerank 客户端会话已关闭，返回空结果。")
            return []

        payload = self._build_payload(
            query=query,
            documents=self._normalize_documents(documents),
            top_n=top_n,
        )

        try:
            async with self.client.post(self.api_url, json=payload) as response:
                if response.status >= 400:
                    response_text = await response.text()
                    raise RuntimeError(
                        f"通用 Rerank API 请求失败: HTTP {response.status}, {response_text}"
                    )

                response_data = await response.json(content_type=None)
        except aiohttp.ClientError as exc:
            logger.error(f"通用 Rerank 请求失败: {exc}")
            raise

        return self._parse_results(response_data)

    async def terminate(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None
