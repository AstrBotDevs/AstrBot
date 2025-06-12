"""
会话插件管理器 - 负责管理每个会话的插件启停状态
"""

from astrbot.core import sp, logger
from typing import Dict, List, Optional
from astrbot.core.platform.astr_message_event import AstrMessageEvent


class SessionPluginManager:
    """管理会话级别的插件启停状态"""
    
    @staticmethod
    def is_plugin_enabled_for_session(session_id: str, plugin_name: str) -> bool:
        """检查插件是否在指定会话中启用
        
        Args:
            session_id: 会话ID (unified_msg_origin)
            plugin_name: 插件名称
            
        Returns:
            bool: True表示启用，False表示禁用
        """
        # 获取会话插件配置
        session_plugin_config = sp.get("session_plugin_config", {})
        session_config = session_plugin_config.get(session_id, {})
        
        enabled_plugins = session_config.get("enabled_plugins", [])
        disabled_plugins = session_config.get("disabled_plugins", [])
        
        # 如果插件在禁用列表中，返回False
        if plugin_name in disabled_plugins:
            return False
            
        # 如果插件在启用列表中，返回True
        if plugin_name in enabled_plugins:
            return True
            
        # 如果都没有配置，默认为启用（兼容性考虑）
        return True
    
    @staticmethod
    def set_plugin_status_for_session(session_id: str, plugin_name: str, enabled: bool) -> None:
        """设置插件在指定会话中的启停状态
        
        Args:
            session_id: 会话ID (unified_msg_origin)
            plugin_name: 插件名称
            enabled: True表示启用，False表示禁用
        """
        # 获取当前配置
        session_plugin_config = sp.get("session_plugin_config", {})
        if session_id not in session_plugin_config:
            session_plugin_config[session_id] = {
                "enabled_plugins": [],
                "disabled_plugins": []
            }
        
        session_config = session_plugin_config[session_id]
        enabled_plugins = session_config.get("enabled_plugins", [])
        disabled_plugins = session_config.get("disabled_plugins", [])
        
        if enabled:
            # 启用插件
            if plugin_name in disabled_plugins:
                disabled_plugins.remove(plugin_name)
            if plugin_name not in enabled_plugins:
                enabled_plugins.append(plugin_name)
        else:
            # 禁用插件
            if plugin_name in enabled_plugins:
                enabled_plugins.remove(plugin_name)
            if plugin_name not in disabled_plugins:
                disabled_plugins.append(plugin_name)
        
        # 保存配置
        session_config["enabled_plugins"] = enabled_plugins
        session_config["disabled_plugins"] = disabled_plugins
        session_plugin_config[session_id] = session_config
        sp.put("session_plugin_config", session_plugin_config)
        
        logger.info(f"会话 {session_id} 的插件 {plugin_name} 状态已更新为: {'启用' if enabled else '禁用'}")
    
    @staticmethod
    def get_session_plugin_config(session_id: str) -> Dict[str, List[str]]:
        """获取指定会话的插件配置
        
        Args:
            session_id: 会话ID (unified_msg_origin)
            
        Returns:
            Dict[str, List[str]]: 包含enabled_plugins和disabled_plugins的字典
        """
        session_plugin_config = sp.get("session_plugin_config", {})
        return session_plugin_config.get(session_id, {
            "enabled_plugins": [],
            "disabled_plugins": []
        })
    
    @staticmethod
    def filter_handlers_by_session(event: AstrMessageEvent, handlers: List) -> List:
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
                
            # 检查插件是否在当前会话中启用
            if SessionPluginManager.is_plugin_enabled_for_session(session_id, plugin.name):
                filtered_handlers.append(handler)
            else:
                logger.debug(f"插件 {plugin.name} 在会话 {session_id} 中被禁用，跳过处理器 {handler.handler_name}")
        
        return filtered_handlers
