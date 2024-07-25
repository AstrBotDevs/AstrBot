import aiohttp
import os

from .base_strategy import RenderStrategy
from type.config import VERSION
from util.io import download_image_by_url

class NetworkRenderStrategy(RenderStrategy):
    def __init__(self) -> None:
        super().__init__()  
        self.BASE_RENDER_URL = "https://t2i.soulter.top/text2img"
        self.TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template")

    async def render(self, text: str, return_url: bool=False) -> str:
        '''
        返回图像的文件路径
        '''
        with open(os.path.join(self.TEMPLATE_PATH, "base.html"), "r", encoding='utf-8') as f:
            tmpl_str = f.read()

        assert(tmpl_str)

        text = text.replace("`", "\`")

        post_data = {
            "tmpl": tmpl_str,
            "json": return_url,
            "tmpldata": {
                "text": text,
                "version": f"v{VERSION}",
            },
            "options": {
                "full_page": True,
                "type": "jpeg",
                "quality": 25,
            }
        }
        
        if return_url:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.BASE_RENDER_URL}/generate", json=post_data) as resp:
                    ret = await resp.json()
                    return f"{self.BASE_RENDER_URL}/{ret['data']['id']}"
        return await download_image_by_url(f"{self.BASE_RENDER_URL}/generate", post=True, post_data=post_data)
