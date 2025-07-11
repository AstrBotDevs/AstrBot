"""
会话服务管理器 - 负责管理每个会话的LLM、TTS等服务的启停状态
"""

from typing import Dict

from astrbot.core import logger, sp
from astrbot.core.platform.astr_message_event import AstrMessageEvent


class SessionServiceManager:
    """管理会话级别的服务启停状态，包括LLM和TTS"""

    # =============================================================================
    # LLM 相关方法
    # =============================================================================

    @staticmethod
    def is_llm_enabled_for_session(session_id: str) -> bool:
        """检查LLM是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用
        """
        # 获取会话服务配置
        session_config = sp.get("session_service_config", {}) or {}
        session_services = session_config.get(session_id, {})

        # 如果配置了该会话的LLM状态，返回该状态
        llm_enabled = session_services.get("llm_enabled")
        if llm_enabled is not None:
            return llm_enabled

        # 如果没有配置，默认为启用（兼容性考虑）
        return True

    @staticmethod
    def set_llm_status_for_session(session_id: str, enabled: bool) -> None:
        """设置LLM在指定会话中的启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用
        """
        # 获取当前配置
        session_config = sp.get("session_service_config", {}) or {}
        if session_id not in session_config:
            session_config[session_id] = {}

        # 设置LLM状态
        session_config[session_id]["llm_enabled"] = enabled

        # 保存配置
        sp.put("session_service_config", session_config)

        logger.info(
            f"会话 {session_id} 的LLM状态已更新为: {'启用' if enabled else '禁用'}"
        )

    @staticmethod
    def should_process_llm_request(event: AstrMessageEvent) -> bool:
        """检查是否应该处理LLM请求

        Args:
            event: 消息事件

        Returns:
            bool: True表示应该处理，False表示跳过
        """
        session_id = event.unified_msg_origin
        return SessionServiceManager.is_llm_enabled_for_session(session_id)

    # =============================================================================
    # TTS 相关方法
    # =============================================================================

    @staticmethod
    def is_tts_enabled_for_session(session_id: str) -> bool:
        """检查TTS是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用
        """
        # 获取会话服务配置
        session_config = sp.get("session_service_config", {}) or {}
        session_services = session_config.get(session_id, {})

        # 如果配置了该会话的TTS状态，返回该状态
        tts_enabled = session_services.get("tts_enabled")
        if tts_enabled is not None:
            return tts_enabled

        # 如果没有配置，默认为启用（兼容性考虑）
        return True

    @staticmethod
    def set_tts_status_for_session(session_id: str, enabled: bool) -> None:
        """设置TTS在指定会话中的启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用
        """
        # 获取当前配置
        session_config = sp.get("session_service_config", {}) or {}
        if session_id not in session_config:
            session_config[session_id] = {}

        # 设置TTS状态
        session_config[session_id]["tts_enabled"] = enabled

        # 保存配置
        sp.put("session_service_config", session_config)

        logger.info(
            f"会话 {session_id} 的TTS状态已更新为: {'启用' if enabled else '禁用'}"
        )

    @staticmethod
    def should_process_tts_request(event: AstrMessageEvent) -> bool:
        """检查是否应该处理TTS请求

        Args:
            event: 消息事件

        Returns:
            bool: True表示应该处理，False表示跳过
        """
        session_id = event.unified_msg_origin
        return SessionServiceManager.is_tts_enabled_for_session(session_id)

    # =============================================================================
    # MCP 相关方法
    # =============================================================================

    @staticmethod
    def is_mcp_enabled_for_session(session_id: str) -> bool:
        """检查MCP是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用
        """
        # 获取会话服务配置
        session_config = sp.get("session_service_config", {}) or {}
        session_services = session_config.get(session_id, {})

        # 如果配置了该会话的MCP状态，返回该状态
        mcp_enabled = session_services.get("mcp_enabled")
        if mcp_enabled is not None:
            return mcp_enabled

        # 如果没有配置，默认为启用（兼容性考虑）
        return True

    @staticmethod
    def set_mcp_status_for_session(session_id: str, enabled: bool) -> None:
        """设置MCP在指定会话中的启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用
        """
        # 获取当前配置
        session_config = sp.get("session_service_config", {}) or {}
        if session_id not in session_config:
            session_config[session_id] = {}

        # 设置MCP状态
        session_config[session_id]["mcp_enabled"] = enabled

        # 保存配置
        sp.put("session_service_config", session_config)

        logger.info(
            f"会话 {session_id} 的MCP状态已更新为: {'启用' if enabled else '禁用'}"
        )

    @staticmethod
    def should_process_mcp_request(event: AstrMessageEvent) -> bool:
        """检查是否应该处理MCP请求

        Args:
            event: 消息事件

        Returns:
            bool: True表示应该处理，False表示跳过
        """
        session_id = event.unified_msg_origin
        return SessionServiceManager.is_mcp_enabled_for_session(session_id)

    # =============================================================================
    # 会话整体启停相关方法
    # =============================================================================

    @staticmethod
    def is_session_enabled(session_id: str) -> bool:
        """检查会话是否整体启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用
        """
        # 获取会话服务配置
        session_config = sp.get("session_service_config", {}) or {}
        session_services = session_config.get(session_id, {})

        # 如果配置了该会话的整体状态，返回该状态
        session_enabled = session_services.get("session_enabled")
        if session_enabled is not None:
            return session_enabled

        # 如果没有配置，默认为启用（兼容性考虑）
        return True

    @staticmethod
    def set_session_status(session_id: str, enabled: bool) -> None:
        """设置会话的整体启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用
        """
        # 获取当前配置
        session_config = sp.get("session_service_config", {}) or {}
        if session_id not in session_config:
            session_config[session_id] = {}

        # 设置会话整体状态
        session_config[session_id]["session_enabled"] = enabled

        # 保存配置
        sp.put("session_service_config", session_config)

        logger.info(
            f"会话 {session_id} 的整体状态已更新为: {'启用' if enabled else '禁用'}"
        )

    @staticmethod
    def should_process_session_request(event: AstrMessageEvent) -> bool:
        """检查是否应该处理会话请求（会话整体启停检查）

        Args:
            event: 消息事件

        Returns:
            bool: True表示应该处理，False表示跳过
        """
        session_id = event.unified_msg_origin
        return SessionServiceManager.is_session_enabled(session_id)

    # =============================================================================
    # 会话命名相关方法
    # =============================================================================

    @staticmethod
    def get_session_custom_name(session_id: str) -> str:
        """获取会话的自定义名称

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            str: 自定义名称，如果没有设置则返回None
        """
        session_config = sp.get("session_service_config", {}) or {}
        session_services = session_config.get(session_id, {})
        return session_services.get("custom_name")

    @staticmethod
    def set_session_custom_name(session_id: str, custom_name: str) -> None:
        """设置会话的自定义名称

        Args:
            session_id: 会话ID (unified_msg_origin)
            custom_name: 自定义名称，可以为空字符串来清除名称
        """
        # 获取当前配置
        session_config = sp.get("session_service_config", {}) or {}
        if session_id not in session_config:
            session_config[session_id] = {}

        # 设置自定义名称
        if custom_name and custom_name.strip():
            session_config[session_id]["custom_name"] = custom_name.strip()
        else:
            # 如果传入空名称，则删除自定义名称
            session_config[session_id].pop("custom_name", None)

        # 保存配置
        sp.put("session_service_config", session_config)

        logger.info(
            f"会话 {session_id} 的自定义名称已更新为: {custom_name.strip() if custom_name and custom_name.strip() else '已清除'}"
        )

    @staticmethod
    def get_session_display_name(session_id: str) -> str:
        """获取会话的显示名称（优先显示自定义名称，否则显示原始session_id的最后一段）

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            str: 显示名称
        """
        custom_name = SessionServiceManager.get_session_custom_name(session_id)
        if custom_name:
            return custom_name

        # 如果没有自定义名称，返回session_id的最后一段
        return session_id.split(":")[2] if session_id.count(":") >= 2 else session_id

    # =============================================================================
    # 通用配置方法
    # =============================================================================

    @staticmethod
    def get_session_service_config(session_id: str) -> Dict[str, bool]:
        """获取指定会话的服务配置

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            Dict[str, bool]: 包含session_enabled、llm_enabled、tts_enabled、mcp_enabled的字典
        """
        session_config = sp.get("session_service_config", {}) or {}
        return session_config.get(
            session_id,
            {
                "session_enabled": True,  # 默认启用
                "llm_enabled": True,  # 默认启用
                "tts_enabled": True,  # 默认启用
                "mcp_enabled": True,  # 默认启用
            },
        )

    @staticmethod
    def get_all_session_configs() -> Dict[str, Dict[str, bool]]:
        """获取所有会话的服务配置

        Returns:
            Dict[str, Dict[str, bool]]: 所有会话的服务配置
        """
        return sp.get("session_service_config", {}) or {}
