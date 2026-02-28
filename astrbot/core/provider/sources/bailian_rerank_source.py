from astrbot.core.lang import t
import os

import aiohttp

from astrbot import logger

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter


class BailianRerankError(Exception):
    """百炼重排序服务异常基类"""

    pass


class BailianAPIError(BailianRerankError):
    """百炼API返回错误"""

    pass


class BailianNetworkError(BailianRerankError):
    """百炼网络请求错误"""

    pass


@register_provider_adapter(
    "bailian_rerank", "阿里云百炼文本排序适配器", provider_type=ProviderType.RERANK
)
class BailianRerankProvider(RerankProvider):
    """阿里云百炼文本重排序适配器."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

        # API配置
        self.api_key = provider_config.get("rerank_api_key") or os.getenv(
            "DASHSCOPE_API_KEY", ""
        )
        if not self.api_key:
            raise ValueError(t("msg-dc1a9e6e"))

        self.model = provider_config.get("rerank_model", "qwen3-rerank")
        self.timeout = provider_config.get("timeout", 30)
        self.return_documents = provider_config.get("return_documents", False)
        self.instruct = provider_config.get("instruct", "")

        self.base_url = provider_config.get(
            "rerank_api_base",
            "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
        )

        # 设置HTTP客户端
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        self.client = aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=self.timeout)
        )

        # 设置模型名称
        self.set_model(self.model)

        logger.info(t("msg-f7079f37", res=self.model))

    def _build_payload(
        self, query: str, documents: list[str], top_n: int | None
    ) -> dict:
        """构建请求载荷

        Args:
            query: 查询文本
            documents: 文档列表
            top_n: 返回前N个结果，如果为None则返回所有结果

        Returns:
            请求载荷字典
        """
        base = {"model": self.model, "input": {"query": query, "documents": documents}}

        params = {
            k: v
            for k, v in [
                ("top_n", top_n if top_n is not None and top_n > 0 else None),
                ("return_documents", True if self.return_documents else None),
                (
                    "instruct",
                    self.instruct
                    if self.instruct and self.model == "qwen3-rerank"
                    else None,
                ),
            ]
            if v is not None
        }

        if params:
            base["parameters"] = params

        return base

    def _parse_results(self, data: dict) -> list[RerankResult]:
        """解析API响应结果

        Args:
            data: API响应数据

        Returns:
            重排序结果列表

        Raises:
            BailianAPIError: API返回错误
            KeyError: 结果缺少必要字段
        """
        # 检查响应状态
        if data.get("code", "200") != "200":
            raise BailianAPIError(
                t("msg-5b6d35ce", res=data.get('code'), res_2=data.get('message', ''))
            )

        results = data.get("output", {}).get("results", [])
        if not results:
            logger.warning(t("msg-d600c5e2", data=data))
            return []

        # 转换为RerankResult对象，使用.get()避免KeyError
        rerank_results = []
        for idx, result in enumerate(results):
            try:
                index = result.get("index", idx)
                relevance_score = result.get("relevance_score", 0.0)

                if relevance_score is None:
                    logger.warning(t("msg-d3312319", idx=idx))
                    relevance_score = 0.0

                rerank_result = RerankResult(
                    index=index, relevance_score=relevance_score
                )
                rerank_results.append(rerank_result)
            except Exception as e:
                logger.warning(t("msg-2855fb44", idx=idx, e=e, result=result))
                continue

        return rerank_results

    def _log_usage(self, data: dict) -> None:
        """记录使用量信息

        Args:
            data: API响应数据
        """
        tokens = data.get("usage", {}).get("total_tokens", 0)
        if tokens > 0:
            logger.debug(t("msg-392f26e8", tokens=tokens))

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        """
        对文档进行重排序

        Args:
            query: 查询文本
            documents: 待排序的文档列表
            top_n: 返回前N个结果，如果为None则使用配置中的默认值

        Returns:
            重排序结果列表
        """
        if not self.client:
            logger.error(t("msg-595e0cf9"))
            return []

        if not documents:
            logger.warning(t("msg-d0388210"))
            return []

        if not query.strip():
            logger.warning(t("msg-44d6cc76"))
            return []

        # 检查限制
        if len(documents) > 500:
            logger.warning(
                t("msg-bd8b942a", res=len(documents))
            )
            documents = documents[:500]

        try:
            # 构建请求载荷，如果top_n为None则返回所有重排序结果
            payload = self._build_payload(query, documents, top_n)

            logger.debug(
                t("msg-0dc3bca4", res=query[:50], res_2=len(documents))
            )

            # 发送请求
            async with self.client.post(self.base_url, json=payload) as response:
                response.raise_for_status()
                response_data = await response.json()

                # 解析结果并记录使用量
                results = self._parse_results(response_data)
                self._log_usage(response_data)

                logger.debug(t("msg-4a9f4ee3", res=len(results)))

                return results

        except aiohttp.ClientError as e:
            error_msg = f"网络请求失败: {e}"
            logger.error(t("msg-fa301307", e=e))
            raise BailianNetworkError(t("msg-10f72727", error_msg=error_msg, e=e)) from e
        except BailianRerankError:
            raise
        except Exception as e:
            error_msg = f"重排序失败: {e}"
            logger.error(t("msg-9879e226", e=e))
            raise BailianRerankError(t("msg-10f72727", error_msg=error_msg, e=e)) from e

    async def terminate(self) -> None:
        """关闭HTTP客户端会话."""
        if self.client:
            logger.info(t("msg-4f15074c"))
            try:
                await self.client.close()
            except Exception as e:
                logger.error(t("msg-d01b1b0f", e=e))
            finally:
                self.client = None
