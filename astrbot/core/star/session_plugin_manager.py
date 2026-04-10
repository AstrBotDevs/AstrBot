"""会话插件管理器 - 负责管理每个会话的插件启停状态"""

from typing import TypedDict

from astrbot.core import logger, sp
from astrbot.core.platform.astr_message_event import AstrMessageEvent


class SessionPluginSettings(TypedDict, total=False):
    enabled_plugins: list[str]
    disabled_plugins: list[str]


def _normalize_session_plugin_config(value: object) -> dict[str, SessionPluginSettings]:
    if not isinstance(value, dict):
        return {}
    config: dict[str, SessionPluginSettings] = {}
    for session_id, raw_settings in value.items():
        if not isinstance(session_id, str) or not isinstance(raw_settings, dict):
            continue
        settings: SessionPluginSettings = {}
        raw_dict: dict[str, object] = raw_settings
        enabled_plugins = raw_dict.get("enabled_plugins")
        if isinstance(enabled_plugins, list) and all(
            isinstance(plugin_name, str) for plugin_name in enabled_plugins
        ):
            settings["enabled_plugins"] = enabled_plugins
        disabled_plugins = raw_dict.get("disabled_plugins")
        if isinstance(disabled_plugins, list) and all(
            isinstance(plugin_name, str) for plugin_name in disabled_plugins
        ):
            settings["disabled_plugins"] = disabled_plugins
        config[session_id] = settings
    return config


class SessionPluginManager:
    """管理会话级别的插件启停状态"""

    @staticmethod
    async def is_plugin_enabled_for_session(session_id: str, plugin_name: str) -> bool:
        """检查插件是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)
            plugin_name: 插件名称

        Returns:
            bool: True表示启用,False表示禁用

        """
        session_plugin_config = _normalize_session_plugin_config(
            await sp.get_async(
                scope="umo",
                scope_id=session_id,
                key="session_plugin_config",
                default={},
            ),
        )
        session_config = session_plugin_config.get(session_id, {})
        enabled_plugins = session_config.get("enabled_plugins", [])
        disabled_plugins = session_config.get("disabled_plugins", [])
        if plugin_name in disabled_plugins:
            return False
        if plugin_name in enabled_plugins:
            return True
        return True

    @staticmethod
    async def filter_handlers_by_session(
        event: AstrMessageEvent, handlers: list,
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
        session_plugin_config = _normalize_session_plugin_config(
            await sp.get_async(
                scope="umo",
                scope_id=session_id,
                key="session_plugin_config",
                default={},
            ),
        )
        session_config = session_plugin_config.get(session_id, {})
        disabled_plugins = session_config.get("disabled_plugins", [])
        for handler in handlers:
            plugin = star_map.get(handler.handler_module_path)
            if not plugin:
                filtered_handlers.append(handler)
                continue
            if plugin.reserved:
                filtered_handlers.append(handler)
                continue
            if plugin.name is None:
                continue
            if plugin.name in disabled_plugins:
                logger.debug(
                    f"插件 {plugin.name} 在会话 {session_id} 中被禁用,跳过处理器 {handler.handler_name}",
                )
            else:
                filtered_handlers.append(handler)
        return filtered_handlers
