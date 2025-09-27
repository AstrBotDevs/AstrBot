
from astrbot.core.utils.io import save_temp_img
from astrbot.core.utils.t2i import RenderStrategy
from astrbot.core.utils.t2i.pillowmd.mdrenderer import PillowMdRenderer
from astrbot.core.utils.t2i.style_manager import StyleManeger

class LocalRenderStrategy(RenderStrategy):
    """本地渲染策略实现"""

    def __init__(self):
        self.style_maneger = StyleManeger()
        self.renderer = PillowMdRenderer()
    
    async def render_custom_template(
        self, tmpl_str: str, tmpl_data: dict, options: dict | None = None
    ) -> str:
        style = self.style_maneger.get_style_from_dict(tmpl_data)
        # 渲染Markdown文本
        image = await self.renderer.md_to_image(text=tmpl_str, style=style)
        # 保存图像并返回路径
        return save_temp_img(image)

    async def render(self, text: str, style_name: str|None=None) -> str:
        style = self.style_maneger.get_style_from_name(style_name)
        # 渲染Markdown文本
        image = await self.renderer.md_to_image(text=text, style=style)
        # 保存图像并返回路径
        return save_temp_img(image)