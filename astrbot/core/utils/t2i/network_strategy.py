import aiohttp
import os
import ssl
import certifi

from . import RenderStrategy
from astrbot.core.config import VERSION
from astrbot.core.utils.io import download_image_by_url

ASTRBOT_T2I_DEFAULT_ENDPOINT = "https://t2i.soulter.top/text2img"


class NetworkRenderStrategy(RenderStrategy):
    def __init__(self, base_url: str = ASTRBOT_T2I_DEFAULT_ENDPOINT) -> None:
        super().__init__()
        if not base_url:
            base_url = ASTRBOT_T2I_DEFAULT_ENDPOINT
        self.BASE_RENDER_URL = base_url
        self.TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template")

        if self.BASE_RENDER_URL.endswith("/"):
            self.BASE_RENDER_URL = self.BASE_RENDER_URL[:-1]
        if not self.BASE_RENDER_URL.endswith("text2img"):
            self.BASE_RENDER_URL += "/text2img"

    def set_endpoint(self, base_url: str):
        if not base_url:
            base_url = ASTRBOT_T2I_DEFAULT_ENDPOINT
        self.BASE_RENDER_URL = base_url

        if self.BASE_RENDER_URL.endswith("/"):
            self.BASE_RENDER_URL = self.BASE_RENDER_URL[:-1]
        if not self.BASE_RENDER_URL.endswith("text2img"):
            self.BASE_RENDER_URL += "/text2img"

    async def render_custom_template(
        self, tmpl_str: str, tmpl_data: dict, return_url: bool = True
    ) -> str:
        """使用自定义文转图模板"""
        post_data = {
            "tmpl": tmpl_str,
            "json": return_url,
            "tmpldata": tmpl_data,
            "options": {
                "full_page": True,
                "type": "jpeg",
                "quality": 40,
            },
        }
        if return_url:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(
                trust_env=True, connector=connector
            ) as session:
                async with session.post(
                    f"{self.BASE_RENDER_URL}/generate", json=post_data
                ) as resp:
                    ret = await resp.json()
                    return f"{self.BASE_RENDER_URL}/{ret['data']['id']}"
        return await download_image_by_url(
            f"{self.BASE_RENDER_URL}/generate", post=True, post_data=post_data
        )

    async def render(self, text: str, return_url: bool = False) -> str:
        """
        返回图像的文件路径
        """
        with open(
            os.path.join(self.TEMPLATE_PATH, "base.html"), "r", encoding="utf-8"
        ) as f:
            tmpl_str = f.read()
        assert tmpl_str
        text = text.replace("`", "\\`")
        return await self.render_custom_template(
            tmpl_str, {"text": text, "version": f"v{VERSION}"}, return_url
        )
