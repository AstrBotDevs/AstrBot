"""会话服务管理器 - 负责管理每个会话的LLM、TTS等服务的启停状态"""

from astrbot.core import logger, sp
from astrbot.core.platform.astr_message_event import AstrMessageEvent


class SessionServiceManager:
    """管理会话级别的服务启停状态，包括LLM和TTS"""

    @staticmethod
    def _group_fallback_umos(session_id: str) -> list[str]:
        """unique_session 开启时，成员级 UMO（形如 ``sender_group``）的群级兜底 UMO。

        未开启 unique_session 时 session_id 不含 ``_`` 分隔，返回空列表，
        行为与之前完全一致。
        """
        parts = session_id.split(":", 2)
        if len(parts) != 3:
            return []
        platform, msg_type, sess = parts
        if msg_type.lower() not in ("groupmessage", "group"):
            return []
        if "_" not in sess:
            return []
        group_id = sess.rsplit("_", 1)[-1]
        if not group_id or group_id == sess:
            return []
        return [f"{platform}:{msg_type}:{group_id}"]

    @staticmethod
    async def _get_service_flag(session_id: str, field: str) -> bool:
        """读取会话服务开关，成员级优先、群级兜底，未配置默认启用。"""
        umos = [session_id, *SessionServiceManager._group_fallback_umos(session_id)]
        for umo in umos:
            session_services = await sp.get_async(
                scope="umo",
                scope_id=umo,
                key="session_service_config",
                default={},
            )
            value = session_services.get(field)
            if value is not None:
                return value
        return True

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
        return await SessionServiceManager._get_service_flag(session_id, "llm_enabled")

    @staticmethod
    async def set_llm_status_for_session(session_id: str, enabled: bool) -> None:
        """设置LLM在指定会话中的启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用

        """
        session_config = (
            await sp.get_async(
                scope="umo",
                scope_id=session_id,
                key="session_service_config",
                default={},
            )
            or {}
        )
        session_config["llm_enabled"] = enabled
        await sp.put_async(
            scope="umo",
            scope_id=session_id,
            key="session_service_config",
            value=session_config,
        )

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
        return await SessionServiceManager._get_service_flag(session_id, "tts_enabled")

    @staticmethod
    async def set_tts_status_for_session(session_id: str, enabled: bool) -> None:
        """设置TTS在指定会话中的启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用

        """
        session_config = (
            await sp.get_async(
                scope="umo",
                scope_id=session_id,
                key="session_service_config",
                default={},
            )
            or {}
        )
        session_config["tts_enabled"] = enabled
        await sp.put_async(
            scope="umo",
            scope_id=session_id,
            key="session_service_config",
            value=session_config,
        )

        logger.info(
            f"TTS status for session {session_id} was updated to "
            f"{'enabled' if enabled else 'disabled'}.",
        )

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
        return await SessionServiceManager._get_service_flag(
            session_id, "session_enabled"
        )
