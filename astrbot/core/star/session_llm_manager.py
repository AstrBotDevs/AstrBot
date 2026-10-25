"""会话服务管理器 - 负责管理每个会话的LLM、TTS等服务的启停状态"""

from astrbot.core import logger, sp
from astrbot.core.platform.astr_message_event import AstrMessageEvent


class SessionServiceManager:
    """管理会话级别的服务启停状态，包括LLM和TTS"""

    @staticmethod
    async def _get_service_flag(
        session_id: str,
        field: str,
        isolated: bool = False,
    ) -> bool:
        """Read a session service toggle: member-level first, group-level fallback.

        The group-level fallback is only applied when ``isolated`` is true, i.e. the
        pipeline confirmed this is a member-isolated group session built by
        ``unique_session`` (session ID ``{sender_id}_{group_id}``). Without that flag
        an ordinary group ID that happens to contain ``_`` must not be reinterpreted.
        """
        umos = [session_id]
        if isolated:
            parts = session_id.split(":", 2)
            if (
                len(parts) == 3
                and parts[1].lower() in ("groupmessage", "group")
                and "_" in parts[2]
            ):
                group_id = parts[2].rsplit("_", 1)[-1]
                if group_id and group_id != parts[2]:
                    umos.append(f"{parts[0]}:{parts[1]}:{group_id}")

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
    async def is_llm_enabled_for_session(session_id: str, isolated: bool = False) -> bool:
        """检查LLM是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)
            isolated: Whether this is a member-isolated unique_session session

        Returns:
            bool: True表示启用，False表示禁用

        """
        return await SessionServiceManager._get_service_flag(
            session_id, "llm_enabled", isolated
        )

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
        isolated = bool(event.get_extra("_session_isolated", False))
        return await SessionServiceManager.is_llm_enabled_for_session(
            session_id, isolated
        )

    # =============================================================================
    # TTS 相关方法
    # =============================================================================

    @staticmethod
    async def is_tts_enabled_for_session(session_id: str, isolated: bool = False) -> bool:
        """检查TTS是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)
            isolated: Whether this is a member-isolated unique_session session

        Returns:
            bool: True表示启用，False表示禁用

        """
        return await SessionServiceManager._get_service_flag(
            session_id, "tts_enabled", isolated
        )

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
        isolated = bool(event.get_extra("_session_isolated", False))
        return await SessionServiceManager.is_tts_enabled_for_session(
            session_id, isolated
        )

    # =============================================================================
    # 会话整体启停相关方法
    # =============================================================================

    @staticmethod
    async def is_session_enabled(session_id: str, isolated: bool = False) -> bool:
        """检查会话是否整体启用

        Args:
            session_id: 会话ID (unified_msg_origin)
            isolated: Whether this is a member-isolated unique_session session

        Returns:
            bool: True表示启用，False表示禁用

        """
        return await SessionServiceManager._get_service_flag(
            session_id, "session_enabled", isolated
        )
