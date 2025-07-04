from .star import StarMetadata
from .star_manager import PluginManager
from .context import Context
from astrbot.core.provider import Provider
from astrbot.core.utils.command_parser import CommandParserMixin
from astrbot.core import html_renderer
from astrbot.core.star.star_tools import StarTools


class Star(CommandParserMixin):
    """所有插件（Star）的父类，所有插件都应该继承于这个类"""

    def __init__(self, context: Context):
        StarTools.initialize(context)
        self.context = context

    @staticmethod
    async def text_to_image(text: str, return_url=True) -> str:
        """将文本转换为图片"""
        return await html_renderer.render_t2i(text, return_url=return_url)

    @staticmethod
    async def html_render(
        tmpl: str, data: dict, return_url=True, options: dict = None
    ) -> str:
        """渲染 HTML"""
        return await html_renderer.render_custom_template(
            tmpl, data, return_url=return_url, options=options
        )

    async def terminate(self):
        """当插件被禁用、重载插件时会调用这个方法"""
        pass


__all__ = ["Star", "StarMetadata", "PluginManager", "Context", "Provider", "StarTools"]
