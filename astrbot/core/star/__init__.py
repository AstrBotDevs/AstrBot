from .star import StarMetadata
# 导入链中检测到循环导入
#   c:\Users\light\Documents\GitHub\AstrBot\astrbot\core\star\__init__.py
#   c:\Users\light\Documents\GitHub\AstrBot\astrbot\core\star\star_manager.py


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

    async def text_to_image(self, text: str, return_url=True) -> str:
        """将文本转换为图片"""
        return await html_renderer.render_t2i(text, return_url=return_url)

    async def html_render(self, tmpl: str, data: dict, return_url=True) -> str:
        """渲染 HTML"""
        return await html_renderer.render_custom_template(
            tmpl, data, return_url=return_url
        )

    async def terminate(self):
        """当插件被禁用、重载插件时会调用这个方法"""
        pass


__all__ = ["Star", "StarMetadata", "PluginManager", "Context", "Provider", "StarTools"]
