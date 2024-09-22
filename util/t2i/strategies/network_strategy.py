import aiohttp
import os

from .base_strategy import RenderStrategy
from type.config import VERSION
from util.io import download_image_by_url

ASTRBOT_T2I_DEFAULT_ENDPOINT = "https://t2i.soulter.top/text2img"

class NetworkRenderStrategy(RenderStrategy):
    def __init__(self, base_url: str = ASTRBOT_T2I_DEFAULT_ENDPOINT) -> None:
        super().__init__()
        if not base_url:
            base_url = ASTRBOT_T2I_DEFAULT_ENDPOINT
        self.BASE_RENDER_URL = base_url
        self.TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template")

    def set_endpoint(self, base_url: str):
        if not base_url:
            base_url = ASTRBOT_T2I_DEFAULT_ENDPOINT
        self.BASE_RENDER_URL = base_url

    async def render_custom_template(self, tmpl_str: str, tmpl_data: dict, return_url: bool=True) -> str:
        '''使用自定义文转图模板'''
        post_data = {
            "tmpl": tmpl_str,
            "json": return_url,
            "tmpldata": tmpl_data,
            "options": {
                "full_page": True,
                "type": "jpeg",
                "quality": 40,
            }
        }
        if return_url:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.BASE_RENDER_URL}/generate", json=post_data) as resp:
                    ret = await resp.json()
                    return f"{self.BASE_RENDER_URL}/{ret['data']['id']}"
        return await download_image_by_url(f"{self.BASE_RENDER_URL}/generate", post=True, post_data=post_data)


    async def render(self, text: str, return_url: bool=False) -> str:
        '''
        返回图像的文件路径
        '''
        with open(os.path.join(self.TEMPLATE_PATH, "base.html"), "r", encoding='utf-8') as f:
            tmpl_str = f.read()
        assert(tmpl_str)
        text = text.replace("`", "\`")
        return await self.render_custom_template(tmpl_str, {"text": text, "version": f"v{VERSION}"}, return_url)