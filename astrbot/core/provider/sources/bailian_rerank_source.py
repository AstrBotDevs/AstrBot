import aiohttp

from astrbot import logger

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter


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
        self.api_key = provider_config.get("rerank_api_key", "")
        if not self.api_key:
            raise ValueError("阿里云百炼 API Key 不能为空。")

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

        logger.info(f"AstrBot 百炼 Rerank 初始化完成。模型: {self.model}")

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
            top_n: 返回前N个结果，如果为None则返回所有重排序结果

        Returns:
            重排序结果列表
        """
        if not documents:
            logger.warning("文档列表为空，返回空结果")
            return []

        if not query.strip():
            logger.warning("查询文本为空，返回空结果")
            return []

        # 检查限制
        if len(documents) > 500:
            logger.warning(
                f"文档数量({len(documents)})超过限制(500)，将截断前500个文档"
            )
            documents = documents[:500]

        try:
            # 构建请求载荷
            payload = {
                "model": self.model,
                "input": {"query": query, "documents": documents},
            }

            # 添加可选参数
            parameters = {}
            if top_n is not None and top_n > 0:
                parameters["top_n"] = top_n
            if self.return_documents:
                parameters["return_documents"] = True
            if self.instruct and self.model == "qwen3-rerank":
                parameters["instruct"] = self.instruct

            if parameters:
                payload["parameters"] = parameters

            logger.debug(
                f"百炼 Rerank 请求: query='{query[:50]}...', 文档数量={len(documents)}"
            )

            # 发送请求
            async with self.client.post(self.base_url, json=payload) as response:
                response.raise_for_status()
                response_data = await response.json()

                # 检查响应状态
                if "code" in response_data and response_data["code"] != "200":
                    error_msg = response_data.get("message", "未知错误")
                    api_error_msg = (
                        f"百炼 API 返回错误: {response_data['code']} - {error_msg}"
                    )
                    raise RuntimeError(api_error_msg)

                # 解析结果
                output = response_data.get("output", {})
                results = output.get("results", [])

                if not results:
                    logger.warning(f"百炼 Rerank 返回空结果: {response_data}")
                    return []

                # 转换为RerankResult对象
                rerank_results = []
                for result in results:
                    rerank_result = RerankResult(
                        index=result["index"], relevance_score=result["relevance_score"]
                    )
                    rerank_results.append(rerank_result)

                logger.debug(f"百炼 Rerank 成功返回 {len(rerank_results)} 个结果")

                # 记录使用量信息
                usage = response_data.get("usage", {})
                total_tokens = usage.get("total_tokens", 0)
                if total_tokens > 0:
                    logger.debug(f"百炼 Rerank 消耗 Token 数量: {total_tokens}")

                return rerank_results

        except aiohttp.ClientError as e:
            error_msg = f"网络请求失败: {e}"
            logger.error(f"百炼 Rerank 网络请求失败: {e}")
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"重排序失败: {e}"
            logger.error(f"百炼 Rerank 处理失败: {e}")
            raise RuntimeError(error_msg) from e

    async def terminate(self) -> None:
        """关闭HTTP客户端会话."""
        if self.client:
            logger.info("关闭 百炼 Rerank 客户端会话")
            try:
                await self.client.close()
            except Exception as e:
                logger.error(f"关闭 百炼 Rerank 客户端时出错: {e}")
            finally:
                self.client = None
