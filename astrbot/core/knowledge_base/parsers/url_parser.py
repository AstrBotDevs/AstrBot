import asyncio

import aiohttp


class URLExtractor:
    """URL 内容提取器，封装了 Tavily API 调用和密钥管理"""

    def __init__(self, tavily_keys: list[str]):
        """
        初始化 URL 提取器

        Args:
            tavily_keys: Tavily API 密钥列表
        """
        if not tavily_keys:
            raise ValueError("Error: Tavily API keys are not configured.")

        self.tavily_keys = tavily_keys
        self.tavily_key_index = 0
        self.tavily_key_lock = asyncio.Lock()

    async def _get_tavily_key(self) -> str:
        """并发安全的从列表中获取并轮换Tavily API密钥。"""
        async with self.tavily_key_lock:
            key = self.tavily_keys[self.tavily_key_index]
            self.tavily_key_index = (self.tavily_key_index + 1) % len(self.tavily_keys)
            return key

    async def extract_text_from_url(self, url: str) -> str:
        """
        使用 Tavily API 从 URL 提取主要文本内容。
        这是 web_searcher 插件中 tavily_extract_web_page 方法的简化版本，
        专门为知识库模块设计，不依赖 AstrMessageEvent。

        Args:
            url: 要提取内容的网页 URL

        Returns:
            提取的文本内容

        Raises:
            ValueError: 如果 URL 为空或 API 密钥未配置
            IOError: 如果请求失败或返回错误
        """
        if not url:
            raise ValueError("Error: url must be a non-empty string.")

        tavily_key = await self._get_tavily_key()
        api_url = "https://api.tavily.com/extract"
        headers = {
            "Authorization": f"Bearer {tavily_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "urls": [url],
            "extract_depth": "basic",  # 使用基础提取深度
        }

        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=30.0,  # 增加超时时间，因为内容提取可能需要更长时间
                ) as response:
                    if response.status != 200:
                        reason = await response.text()
                        raise OSError(
                            f"Tavily web extraction failed: {reason}, status: {response.status}"
                        )

                    data = await response.json()
                    results = data.get("results", [])

                    if not results:
                        raise ValueError(f"No content extracted from URL: {url}")

                    # 返回第一个结果的内容
                    return results[0].get("raw_content", "")

        except aiohttp.ClientError as e:
            raise OSError(f"Failed to fetch URL {url}: {e}") from e
        except Exception as e:
            raise OSError(f"Failed to extract content from URL {url}: {e}") from e


# 为了向后兼容，提供一个简单的函数接口
async def extract_text_from_url(url: str, tavily_keys: list[str]) -> str:
    """
    简单的函数接口，用于从 URL 提取文本内容

    Args:
        url: 要提取内容的网页 URL
        tavily_keys: Tavily API 密钥列表

    Returns:
        提取的文本内容
    """
    extractor = URLExtractor(tavily_keys)
    return await extractor.extract_text_from_url(url)
