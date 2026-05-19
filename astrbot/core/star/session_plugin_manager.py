"""会话插件管理器 - 负责管理每个会话的插件启停状态"""

from astrbot.core import logger, sp
from astrbot.core.platform.astr_message_event import AstrMessageEvent


class SessionPluginManager:
    """管理会话级别的插件启停状态"""

    @staticmethod
    async def get_session_plugin_config(session_id: str) -> dict:
        """获取指定会话的插件配置。"""
        session_plugin_config = await sp.get_async(
            scope="umo",
            scope_id=session_id,
            key="session_plugin_config",
            default={},
        )
        return session_plugin_config.get(session_id, {})

    @staticmethod
    def is_plugin_enabled_for_session_config(
        plugin_name: str | None,
        session_config: dict | None,
        *,
        reserved: bool = False,
    ) -> bool:
        """检查插件是否在指定会话配置中启用。"""
        if reserved or not plugin_name:
            return True

        if not session_config:
            return True

        enabled_plugins = session_config.get("enabled_plugins", [])
        disabled_plugins = session_config.get("disabled_plugins", [])

        if plugin_name in disabled_plugins:
            return False

        if plugin_name in enabled_plugins:
            return True

        return True

    @staticmethod
    async def is_plugin_enabled_for_session(
        session_id: str,
        plugin_name: str,
        *,
        reserved: bool = False,
    ) -> bool:
        """检查插件是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)
            plugin_name: 插件名称

        Returns:
            bool: True表示启用，False表示禁用

        """
        session_config = await SessionPluginManager.get_session_plugin_config(
            session_id
        )
        return SessionPluginManager.is_plugin_enabled_for_session_config(
            plugin_name,
            session_config,
            reserved=reserved,
        )

    @staticmethod
    async def filter_handlers_by_session(
        event: AstrMessageEvent,
        handlers: list,
    ) -> list:
        """根据会话配置过滤处理器列表

        Args:
            event: 消息事件
            handlers: 原始处理器列表

        Returns:
            List: 过滤后的处理器列表

        """
        from astrbot.core.star.star import star_map

        session_id = event.unified_msg_origin
        filtered_handlers = []

        session_config = await SessionPluginManager.get_session_plugin_config(
            session_id
        )

        for handler in handlers:
            # 获取处理器对应的插件
            plugin = star_map.get(handler.handler_module_path)
            if not plugin:
                # 如果找不到插件元数据，允许执行（可能是系统插件）
                filtered_handlers.append(handler)
                continue

            # 跳过保留插件（系统插件）
            if plugin.reserved:
                filtered_handlers.append(handler)
                continue

            if plugin.name is None:
                continue

            # 检查插件是否在当前会话中启用
            if not SessionPluginManager.is_plugin_enabled_for_session_config(
                plugin.name,
                session_config,
                reserved=plugin.reserved,
            ):
                logger.debug(
                    f"插件 {plugin.name} 在会话 {session_id} 中被禁用，跳过处理器 {handler.handler_name}",
                )
            else:
                filtered_handlers.append(handler)

        return filtered_handlers
