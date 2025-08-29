import aiohttp
import asyncio
import os
import ssl
import certifi
import logging
import random
from . import RenderStrategy
from astrbot.core.config import VERSION
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

ASTRBOT_T2I_DEFAULT_ENDPOINT = "https://t2i.soulter.top/text2img"
CUSTOM_T2I_TEMPLATE_PATH = os.path.join(get_astrbot_data_path(), "t2i_template.html")

logger = logging.getLogger("astrbot")


class NetworkRenderStrategy(RenderStrategy):
    def __init__(self, base_url: str | None = None) -> None:
        super().__init__()
        if not base_url:
            self.BASE_RENDER_URL = ASTRBOT_T2I_DEFAULT_ENDPOINT
        else:
            self.BASE_RENDER_URL = self._clean_url(base_url)
        self.TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template", "base.html")
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            self.DEFAULT_TEMPLATE = f.read()

        self.endpoints = [self.BASE_RENDER_URL]

    async def initialize(self):
        if self.BASE_RENDER_URL == ASTRBOT_T2I_DEFAULT_ENDPOINT:
            asyncio.create_task(self.get_official_endpoints())

    async def get_template(self) -> str:
        """获取文转图 HTML 模板

        Returns:
            str: 文转图 HTML 模板字符串
        """
        if os.path.exists(CUSTOM_T2I_TEMPLATE_PATH):
            with open(CUSTOM_T2I_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                return f.read()
        return self.DEFAULT_TEMPLATE

    async def get_official_endpoints(self):
        """获取官方的 t2i 端点列表。"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.soulter.top/astrbot/t2i-endpoints"
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        all_endpoints: list[dict] = data.get("data", [])
                        self.endpoints = [
                            ep.get("url")
                            for ep in all_endpoints
                            if ep.get("active") and ep.get("url")
                        ]
                        logger.info(
                            f"Successfully got {len(self.endpoints)} official T2I endpoints."
                        )
        except Exception as e:
            logger.error(f"Failed to get official endpoints: {e}")

    def _clean_url(self, url: str):
        if url.endswith("/"):
            url = url[:-1]
        if not url.endswith("text2img"):
            url += "/text2img"
        return url

    async def render_custom_template(
        self,
        tmpl_str: str,
        tmpl_data: dict,
        return_url: bool = True,
        options: dict | None = None,
    ) -> str:
        """使用自定义文转图模板"""

        default_options = {"full_page": True, "type": "jpeg", "quality": 40}
        if options:
            default_options |= options

        post_data = {
            "tmpl": tmpl_str,
            "json": return_url,
            "tmpldata": tmpl_data,
            "options": default_options,
        }

        endpoints = self.endpoints.copy() if self.endpoints else [self.BASE_RENDER_URL]
        random.shuffle(endpoints)
        last_exception = None
        for endpoint in endpoints:
            try:
                if return_url:
                    ssl_context = ssl.create_default_context(cafile=certifi.where())
                    connector = aiohttp.TCPConnector(ssl=ssl_context)
                    async with aiohttp.ClientSession(
                        trust_env=True, connector=connector
                    ) as session:
                        async with session.post(
                            f"{endpoint}/generate", json=post_data
                        ) as resp:
                            if resp.status == 200:
                                ret = await resp.json()
                                return f"{endpoint}/{ret['data']['id']}"
                            else:
                                raise Exception(f"HTTP {resp.status}")
                else:
                    # download_image_by_url 失败时抛异常
                    return await download_image_by_url(
                        f"{endpoint}/generate", post=True, post_data=post_data
                    )
            except Exception as e:
                last_exception = e
                logger.warning(f"Endpoint {endpoint} failed: {e}, trying next...")
                continue
        # 全部失败
        logger.error(f"All endpoints failed: {last_exception}")
        raise RuntimeError(f"All endpoints failed: {last_exception}")

    async def render(self, text: str, return_url: bool = False) -> str:
        """
        返回图像的文件路径
        """
        tmpl_str = await self.get_template()
        text = text.replace("`", "\\`")
        return await self.render_custom_template(
            tmpl_str, {"text": text, "version": f"v{VERSION}"}, return_url
        )
