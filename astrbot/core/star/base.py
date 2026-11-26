from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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

    def _active_metadata(self) -> StarMetadata | None:
        metadata = star_map.get(type(self).__module__)
        if metadata is not None and metadata.activated and metadata.star_cls is self:
            return metadata
        return None

    async def schedule_continuation(self, user_prompt: str) -> bool:
        """Enqueue a managed main-agent continuation for the current session.

        A managed continuation can schedule another turn only through the
        plugin instance that started it. Other plugins can still observe it.

        Args:
            user_prompt: Model input for the next turn.

        Returns:
            True when queued, or False when another plugin owns the current
            continuation or the source event stops before submission.

        Raises:
            RuntimeError: If invoked without an active event or by an inactive plugin.
            ValueError: If the target adapter is unavailable or the prompt is empty.
        """
        from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
        from astrbot.core.platform.astr_message_event import (
            _continuation_owner,
            current_message_event,
        )
        from astrbot.core.platform.message_session import MessageSession
        from astrbot.core.utils.active_event_registry import active_event_registry

        owner = _continuation_owner.get()
        if owner is not None and owner is not self:
            return False
        metadata = self._active_metadata()
        origin = current_message_event.get()
        if metadata is None:
            raise RuntimeError("Continuation requires an active plugin instance")
        if origin is None or not origin._execution_active:
            raise RuntimeError("Continuation requires an active message event")
        stop_signal = active_event_registry.get_background_stop_signal(origin)
        if stop_signal.is_set():
            return False
        if not user_prompt.strip():
            raise ValueError("Continuation requires a non-empty prompt")
        platform = self.context.get_platform_inst(origin.session.platform_id)
        if platform is None:
            raise ValueError("Continuation target adapter is unavailable")

        umo = origin.unified_msg_origin
        target = await self.context.agent._continuation_target(origin)
        if stop_signal.is_set():
            return False
        if not origin._execution_active:
            raise RuntimeError("Continuation requires an active message event")

        event = AgentWakeupEvent(
            context=self.context,
            session=MessageSession.from_str(umo),
            platform_meta=platform.meta(),
            prompt=user_prompt,
            source="plugin",
            source_id=metadata.name,
            role=origin.role,
            agent_session=target,
            source_event=origin,
        )
        event._continuation_owner = self
        active_event_registry.register_pending_continuation(event)
        try:
            await self.context.get_event_queue().put(event)
        except BaseException:
            active_event_registry.discard_pending_continuation(event)
            raise
        return True

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
        """当插件被禁用、重载插件时会调用这个方法"""

    def __del__(self) -> None:
        """[Deprecated] 当插件被禁用、重载插件时会调用这个方法"""
