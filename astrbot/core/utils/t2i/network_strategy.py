import aiohttp
import asyncio
import ssl
import certifi
import logging
import random
from . import RenderStrategy
from astrbot.core.config import VERSION
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.t2i.template_manager import TemplateManager

ASTRBOT_T2I_DEFAULT_ENDPOINT = "https://t2i.soulter.top/text2img"

logger = logging.getLogger("astrbot")


class NetworkRenderStrategy(RenderStrategy):
    def __init__(self, base_url: str | None = None) -> None:
        super().__init__()
        if not base_url:
            self.BASE_RENDER_URL = ASTRBOT_T2I_DEFAULT_ENDPOINT
        else:
            self.BASE_RENDER_URL = self._clean_url(base_url)

        self.endpoints = [self.BASE_RENDER_URL]
        self.template_manager = TemplateManager()

    async def initialize(self):
        if self.BASE_RENDER_URL == ASTRBOT_T2I_DEFAULT_ENDPOINT:
            asyncio.create_task(self.get_official_endpoints())

    async def get_template(self, name: str = "base") -> str:
        """通过名称获取文转图 HTML 模板"""
        return self.template_manager.get_template(name)

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

    async def render(
        self, text: str, return_url: bool = False, template_name: str | None = "base"
    ) -> str:
        """
        返回图像的文件路径
        """
        if not template_name:
            template_name = "base"
        tmpl_str = await self.get_template(name=template_name)
        text = text.replace("`", "\\`")
        return await self.render_custom_template(
            tmpl_str, {"text": text, "version": f"v{VERSION}"}, return_url
        )
