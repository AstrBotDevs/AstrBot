from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from astrbot.core import html_renderer
from astrbot.core.log import LogManager
from astrbot.core.utils.command_parser import CommandParserMixin
from astrbot.core.utils.plugin_kv_store import PluginKVStoreMixin

from .star import StarMetadata, star_map, star_registry

if TYPE_CHECKING:
    from .context import Context

logger = logging.getLogger("astrbot")


class Star(CommandParserMixin, PluginKVStoreMixin):
    """所有插件（Star）的父类，所有插件都应该继承于这个类"""

    author: str
    name: str
    context: Context
    logger: logging.Logger
    """The plugin's dedicated logger, isolated from the global ``astrbot`` logger."""

    def __init__(self, context: Context, config: dict | None = None) -> None:
        self.context = context
        # Resolve the plugin name from the metadata registered for this module
        # first (it matches the name the dashboard uses); the loader also
        # injects a sanitized ``name`` class attribute as a fallback. When both
        # are absent (e.g. direct instantiation in tests), fall back to the
        # global logger.
        metadata = star_map.get(self.__class__.__module__)
        plugin_name = (metadata.name if metadata else None) or getattr(
            self, "name", None
        )
        try:
            self.logger = (
                LogManager.get_plugin_logger(plugin_name)
                if plugin_name
                else logging.getLogger("astrbot")
            )
            logger.info(
                "Plugin %s log level: %s.",
                plugin_name or self.__class__.__name__,
                logging.getLevelName(self.logger.getEffectiveLevel()),
            )
        except AttributeError:
            # The plugin defines ``logger`` as a read-only property; keep its own.
            pass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not star_map.get(cls.__module__):
            metadata = StarMetadata(
                star_cls_type=cls,
                module_path=cls.__module__,
            )
            star_map[cls.__module__] = metadata
            star_registry.append(metadata)
        else:
            star_map[cls.__module__].star_cls_type = cls
            star_map[cls.__module__].module_path = cls.__module__

    async def text_to_image(
        self,
        text: str,
        return_url: bool = True,
        template_name: str | None = None,
        umo: str | None = None,
    ) -> str:
        """Convert text to an image using the t2i render service.

        Args:
            text: The text to render.
            return_url: Whether to return an image URL instead of a file path.
            template_name: Explicit t2i template name. Takes precedence over
                the `t2i_active_template` value from any configuration file.
            umo: The unified_message_origin used to resolve the bound
                configuration file. Only consulted when `template_name` is not
                given; falls back to the default configuration file when the
                session has no bound configuration.

        Returns:
            The image URL or file path, depending on `return_url`.
        """
        if template_name is None:
            template_name = self.context.get_config(umo).get("t2i_active_template")
        return await html_renderer.render_t2i(
            text,
            return_url=return_url,
            template_name=template_name,
        )

    async def html_render(
        self,
        tmpl: str,
        data: dict,
        return_url=True,
        options: dict | None = None,
    ) -> str:
        """渲染 HTML"""
        return await html_renderer.render_custom_template(
            tmpl,
            data,
            return_url=return_url,
            options=options,
        )

    async def initialize(self) -> None:
        """当插件被激活时会调用这个方法"""

    async def terminate(self) -> None:
        """当插件被禁用、重载插件时会调用这个方法"""

    def __del__(self) -> None:
        """[Deprecated] 当插件被禁用、重载插件时会调用这个方法"""
