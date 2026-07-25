import logging
from typing import TYPE_CHECKING, Any

from astrbot.core.log import LogManager
from astrbot.core.utils.plugin_kv_store import PluginKVStoreMixin

from .star import StarDeclaration

if TYPE_CHECKING:
    from .plugin_context import PluginContext

logger = logging.getLogger("astrbot")


class Star(PluginKVStoreMixin):
    """所有插件（Star）的父类，所有插件都应该继承于这个类"""

    author: str
    name: str
    context: PluginContext
    logger: logging.Logger

    def __init__(self, context: PluginContext, config: dict | None = None) -> None:
        self.context = context
        plugin_name = getattr(self.__class__, "__astrbot_plugin_logger_name__", None)
        self.logger = (
            LogManager.get_plugin_logger(plugin_name)
            if isinstance(plugin_name, str) and plugin_name
            else logging.getLogger("astrbot")
        )

    def _get_context_config(self) -> Any:
        try:
            return self.context.config.get()
        except Exception as exc:
            logger.debug("Unable to resolve plugin configuration: %s", exc)
            return None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__astrbot_star_declaration__ = StarDeclaration(
            star_cls_type=cls,
            module_path=cls.__module__,
        )

    async def text_to_image(self, text: str) -> str:
        """将文本转换为图片"""
        config_obj = self._get_context_config()
        template_name = None
        if hasattr(config_obj, "get"):
            try:
                template_name = config_obj.get("t2i_active_template")
            except Exception:
                template_name = None
        return await self.context.rendering.text_to_image(
            text,
            template_name=template_name,
        )

    async def html_render(
        self,
        tmpl: str,
        data: dict,
        options: dict | None = None,
    ) -> str:
        """渲染 HTML"""
        return await self.context.rendering.html(
            tmpl,
            data,
            options=options,
        )

    async def initialize(self) -> None:
        """当插件被激活时会调用这个方法"""

    async def terminate(self) -> None:
        """当插件被禁用、重载插件时会调用这个方法"""

    def __del__(self) -> None:
        """[Deprecated] 当插件被禁用、重载插件时会调用这个方法"""
