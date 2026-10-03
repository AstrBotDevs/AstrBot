from __future__ import annotations

import logging
from asyncio import Queue
from typing import TYPE_CHECKING, Any, Protocol

from astrbot.core.log import LogManager
from astrbot.core.utils.command_parser import CommandParserMixin
from astrbot.core.utils.plugin_kv_store import PluginKVStoreMixin

from .star import StarMetadata, star_map, star_registry

if TYPE_CHECKING:
    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.conversation_mgr import ConversationManager
    from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
    from astrbot.core.provider.func_tool_manager import FunctionToolManager
    from astrbot.core.provider.manager import ProviderManager
    from astrbot.core.provider.provider import Provider
    from astrbot.core.utils.t2i.renderer import HtmlRenderer

logger = logging.getLogger("astrbot")


class Star(CommandParserMixin, PluginKVStoreMixin):
    """所有插件(Star)的父类,所有插件都应该继承于这个类"""

    author: str
    name: str
    context: _ContextLike
    logger: logging.Logger
    """The plugin's dedicated logger, isolated from the global ``astrbot`` logger."""

    class _ContextLike(Protocol):
        html_renderer: HtmlRenderer

        def get_config(self, umo: str | None = None) -> AstrBotConfig: ...

        def get_using_provider(self, umo: str | None = None) -> Provider | None: ...

        async def get_using_provider_async(
            self, umo: str | None = None
        ) -> Provider | None: ...

        def get_llm_tool_manager(self) -> FunctionToolManager: ...

        def get_event_queue(self) -> Queue[Any]: ...

        @property
        def conversation_manager(self) -> ConversationManager: ...

        @property
        def message_history_manager(self) -> PlatformMessageHistoryManager: ...

        @property
        def provider_manager(self) -> ProviderManager: ...

    def __init__(self, context: _ContextLike, config: dict | None = None) -> None:
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

        The renderer is held on the context: plugins can also call
        `self.context.html_renderer` directly for lower-level control.

        Args:
            text: The text to render.
            return_url: Whether to return an image URL instead of a file path.
            template_name: Explicit t2i template name. Takes precedence over
                the `t2i_active_template` value from any configuration file.
            umo: The unified_message_origin used to resolve the bound
                configuration file. Template and render endpoint are read from
                that configuration; falls back to the default configuration
                file when the session has no bound configuration.

        Returns:
            The image URL or file path, depending on `return_url`.
        """
        config = self.context.get_config(umo)
        endpoint = None
        if config is not None:
            if template_name is None:
                template_name = config.get("t2i_active_template")
            endpoint = config.get("t2i_endpoint") or None
        return await self.context.html_renderer.render_t2i(
            text,
            return_url=return_url,
            template_name=template_name,
            endpoint=endpoint,
        )

    async def html_render(
        self,
        tmpl: str,
        data: dict,
        return_url: bool = True,
        options: dict | None = None,
        umo: str | None = None,
    ) -> str:
        """Render a custom Jinja2 HTML template to an image.

        The renderer is held on the context: plugins can also call
        `self.context.html_renderer` directly for lower-level control.

        Args:
            tmpl: The HTML Jinja2 template string.
            data: The template data.
            return_url: Whether to return an image URL instead of a file path.
            options: Render options passed to the render service.
            umo: The unified_message_origin used to resolve the render
                endpoint from the bound configuration file. Falls back to the
                default configuration file when omitted or unbound.

        Returns:
            The image URL or file path, depending on `return_url`.
        """
        config = self.context.get_config(umo)
        endpoint = None
        if config is not None:
            endpoint = config.get("t2i_endpoint") or None
        return await self.context.html_renderer.render_custom_template(
            tmpl,
            data,
            return_url=return_url,
            options=options,
            endpoint=endpoint,
        )

    async def initialize(self) -> None:
        """当插件被激活时会调用这个方法"""

    async def terminate(self) -> None:
        """当插件被禁用､重载插件时会调用这个方法"""

    def __del__(self) -> None:
        """[Deprecated] 当插件被禁用､重载插件时会调用这个方法"""
