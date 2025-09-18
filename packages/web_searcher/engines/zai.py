"""Z.AI WebSearch API wrapper for AstrBot web searcher"""

import aiohttp
import asyncio
import random
from typing import List, Dict, Any, Union
from . import SearchResult
from astrbot.api import logger


class ZAIError(Exception):
    """Base exception for ZAI API errors"""

    pass


class ZAIAPIError(ZAIError):
    """Exception raised when ZAI API returns an error response"""

    pass


class ZAITimeoutError(ZAIError):
    """Exception raised when ZAI API request times out"""

    pass


class ZAI:
    """Z.AI WebSearch API wrapper with multiple API keys support"""

    SEARCH_ENGINES = {
        "search_std": "基础版（智谱AI 自研）",
        "search_pro": "高级版（智谱AI 自研）",
        "search_pro_sogou": "搜狗",
        "search_pro_quark": "夸克",
    }

    def __init__(
        self, api_keys: Union[str, List[str]], search_engine: str = "search_pro"
    ):
        if isinstance(api_keys, str):
            self.api_keys = [key.strip() for key in api_keys.split(",") if key.strip()]
        elif isinstance(api_keys, list):
            self.api_keys = [key.strip() for key in api_keys if key and key.strip()]
        else:
            raise ValueError("API Keys 必须是字符串或字符串列表")

        if not self.api_keys:
            raise ValueError("至少需要提供一个有效的 API Key")

        self.search_engine = (
            search_engine if search_engine in self.SEARCH_ENGINES else "search_pro"
        )
        self.base_url = "https://open.bigmodel.cn/api/paas/v4"
        self.timeout = 30

    def _get_random_api_key(self) -> str:
        """随机选择一个API Key进行负载均衡"""
        return random.choice(self.api_keys)

    def _build_headers(self, api_key: str) -> Dict[str, str]:
        """构建请求头"""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        query: str,
        count: int,
        search_domain_filter: str,
        search_recency_filter: str,
        content_size: str,
    ) -> Dict[str, Any]:
        """构建请求参数"""
        payload = {
            "search_engine": self.search_engine,
            "search_query": query,
            "count": min(max(count, 1), 50),
        }

        if search_domain_filter:
            payload["search_domain_filter"] = search_domain_filter
        if search_recency_filter != "noLimit":
            payload["search_recency_filter"] = search_recency_filter
        if content_size in {"low", "medium", "high"}:
            payload["content_size"] = content_size

        return payload

    async def search(
        self,
        query: str,
        count: int = 10,
        search_domain_filter: str = "",
        search_recency_filter: str = "oneMonth",
        content_size: str = "high",
    ) -> List[SearchResult]:
        """使用 Z.AI Web Search API 进行搜索"""
        api_key = self._get_random_api_key()
        headers = self._build_headers(api_key)
        payload = self._build_payload(
            query, count, search_domain_filter, search_recency_filter, content_size
        )

        logger.info(f"ZAI搜索 - 查询: {query} | 引擎: {self.search_engine}")

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                async with session.post(
                    f"{self.base_url}/web_search",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ZAIAPIError(
                            f"ZAI API错误: {response.status} - {error_text}"
                        )

                    data = await response.json()
                    results = self._parse_search_results(data)
                    logger.info(f"ZAI搜索完成 - 返回 {len(results)} 个结果")
                    return results

            except asyncio.TimeoutError as e:
                raise ZAITimeoutError("ZAI API请求超时") from e
            except Exception as e:
                logger.error(f"ZAI搜索失败: {e}")
                raise

    def _parse_search_results(self, data: Dict[str, Any]) -> List[SearchResult]:
        """解析搜索结果"""
        results = []
        for item in data.get("search_result", []):
            title = item.get("title", "")
            url = item.get("link", "")
            content = item.get("content", "")

            if title and url:
                results.append(SearchResult(title=title, url=url, snippet=content))

        return results
