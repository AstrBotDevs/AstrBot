import asyncio

import aiohttp

# 支持从 URL 提取正文内容的网页搜索提供商。
# 其余提供商（bocha、brave、baidu_ai_search 等）暂不支持单页内容提取。
SUPPORTED_URL_EXTRACT_PROVIDERS = ("tavily", "firecrawl")


def _normalize_keys(keys: str | list[str] | None) -> list[str]:
    """将密钥配置规范化为列表。

    兼容历史配置中将单个密钥存为字符串的情况，避免 list("key") 把字符串
    拆成单个字符。
    """
    if isinstance(keys, str):
        return [keys] if keys else []
    return list(keys or [])


class URLExtractor:
    """URL 内容提取器，封装 Tavily / Firecrawl API 调用和密钥轮换。

    与 web_searcher 内置工具保持一致地支持多个网页搜索提供商，但这里是
    专门为知识库模块设计的简化版本，不依赖 AstrMessageEvent。
    """

    def __init__(
        self,
        tavily_keys: str | list[str] | None = None,
        *,
        provider: str = "tavily",
        firecrawl_keys: str | list[str] | None = None,
    ) -> None:
        """
        初始化 URL 提取器

        Args:
            tavily_keys: Tavily API 密钥列表
            provider: URL 内容提取所用的提供商（"tavily" 或 "firecrawl"）
            firecrawl_keys: Firecrawl API 密钥列表
        """
        self.provider = (provider or "tavily").lower()
        if self.provider not in SUPPORTED_URL_EXTRACT_PROVIDERS:
            raise ValueError(
                f"Error: Unsupported URL extraction provider '{self.provider}'. "
                f"Supported providers: {', '.join(SUPPORTED_URL_EXTRACT_PROVIDERS)}."
            )

        self._keys: dict[str, list[str]] = {
            "tavily": _normalize_keys(tavily_keys),
            "firecrawl": _normalize_keys(firecrawl_keys),
        }
        if not self._keys[self.provider]:
            raise ValueError(
                f"Error: {self.provider.capitalize()} API keys are not configured."
            )

        self._key_index = 0
        self._key_lock = asyncio.Lock()

    async def _get_key(self) -> str:
        """并发安全地从当前提供商的密钥列表中获取并轮换 API 密钥。"""
        keys = self._keys[self.provider]
        async with self._key_lock:
            key = keys[self._key_index]
            self._key_index = (self._key_index + 1) % len(keys)
            return key

    async def extract_text_from_url(self, url: str) -> str:
        """
        使用已配置的提供商从 URL 提取主要文本内容。

        Args:
            url: 要提取内容的网页 URL

        Returns:
            提取的文本内容

        Raises:
            ValueError: 如果 URL 为空或未提取到内容
            IOError: 如果请求失败或返回错误
        """
        if not url:
            raise ValueError("Error: url must be a non-empty string.")

        if self.provider == "firecrawl":
            return await self._extract_with_firecrawl(url)
        return await self._extract_with_tavily(url)

    async def _extract_with_tavily(self, url: str) -> str:
        """使用 Tavily API 从 URL 提取主要文本内容。"""
        tavily_key = await self._get_key()
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
        except (ValueError, OSError):
            raise
        except Exception as e:
            raise OSError(f"Failed to extract content from URL {url}: {e}") from e

    async def _extract_with_firecrawl(self, url: str) -> str:
        """使用 Firecrawl Scrape API 从 URL 提取主要文本内容（Markdown）。"""
        firecrawl_key = await self._get_key()
        api_url = "https://api.firecrawl.dev/v2/scrape"
        headers = {
            "Authorization": f"Bearer {firecrawl_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
        }

        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                ) as response:
                    if response.status != 200:
                        reason = await response.text()
                        raise OSError(
                            f"Firecrawl web extraction failed: {reason}, status: {response.status}"
                        )

                    data = await response.json()
                    result = data.get("data", {})
                    content = result.get("markdown", "") if result else ""

                    if not content:
                        raise ValueError(f"No content extracted from URL: {url}")

                    return content

        except aiohttp.ClientError as e:
            raise OSError(f"Failed to fetch URL {url}: {e}") from e
        except (ValueError, OSError):
            raise
        except Exception as e:
            raise OSError(f"Failed to extract content from URL {url}: {e}") from e


# 为了向后兼容，提供一个简单的函数接口
async def extract_text_from_url(
    url: str,
    tavily_keys: str | list[str] | None = None,
    *,
    provider: str = "tavily",
    firecrawl_keys: str | list[str] | None = None,
) -> str:
    """
    简单的函数接口，用于从 URL 提取文本内容

    Args:
        url: 要提取内容的网页 URL
        tavily_keys: Tavily API 密钥列表
        provider: URL 内容提取所用的提供商（"tavily" 或 "firecrawl"）
        firecrawl_keys: Firecrawl API 密钥列表

    Returns:
        提取的文本内容
    """
    extractor = URLExtractor(
        tavily_keys,
        provider=provider,
        firecrawl_keys=firecrawl_keys,
    )
    return await extractor.extract_text_from_url(url)
