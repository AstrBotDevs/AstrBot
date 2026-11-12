"""会话服务管理器 - 负责管理每个会话的LLM、TTS等服务的启停状态"""

from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.session_overrides import get_overrides, update_overrides


class SessionServiceManager:
    """管理会话级别的服务启停状态，包括LLM和TTS"""

    # =============================================================================
    # LLM 相关方法
    # =============================================================================

    @staticmethod
    async def is_llm_enabled_for_session(session_id: str) -> bool:
        """检查LLM是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用

        """
        # 获取会话服务配置
        session_services = await get_overrides(session_id)

        # 如果配置了该会话的LLM状态，返回该状态
        llm_enabled = session_services.get("provider_settings.enable")
        if llm_enabled is not None:
            return llm_enabled

        # 如果没有配置，默认为启用（兼容性考虑）
        return True

    @staticmethod
    async def set_llm_status_for_session(session_id: str, enabled: bool) -> None:
        """设置LLM在指定会话中的启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用

        """
        await update_overrides(session_id, {"provider_settings.enable": enabled})

    @staticmethod
    async def should_process_llm_request(event: AstrMessageEvent) -> bool:
        """检查是否应该处理LLM请求

        Args:
            event: 消息事件

        Returns:
            bool: True表示应该处理，False表示跳过

        """
        session_id = event.unified_msg_origin
        return await SessionServiceManager.is_llm_enabled_for_session(session_id)

    # =============================================================================
    # TTS 相关方法
    # =============================================================================

    @staticmethod
    async def is_tts_enabled_for_session(session_id: str) -> bool:
        """检查TTS是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用

        """
        # 获取会话服务配置
        session_services = await get_overrides(session_id)

        # 如果配置了该会话的TTS状态，返回该状态
        tts_enabled = session_services.get("provider_tts_settings.enable")
        if tts_enabled is not None:
            return tts_enabled

        # 如果没有配置，默认为启用（兼容性考虑）
        return True

    @staticmethod
    async def set_tts_status_for_session(session_id: str, enabled: bool) -> None:
        """设置TTS在指定会话中的启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用

        """
        await update_overrides(session_id, {"provider_tts_settings.enable": enabled})

    @staticmethod
    async def should_process_tts_request(event: AstrMessageEvent) -> bool:
        """检查是否应该处理TTS请求

        Args:
            event: 消息事件

        Returns:
            bool: True表示应该处理，False表示跳过

        """
        session_id = event.unified_msg_origin
        return await SessionServiceManager.is_tts_enabled_for_session(session_id)

    # =============================================================================
    # 会话整体启停相关方法
    # =============================================================================

    @staticmethod
    async def is_session_enabled(session_id: str) -> bool:
        """检查会话是否整体启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用

        """
        overrides = await get_overrides(session_id)
        return session_id not in overrides.get("platform_settings.id_blacklist", [])
