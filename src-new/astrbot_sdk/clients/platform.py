"""平台客户端模块。

提供 v4 原生的平台能力调用。

设计边界：
    - `PlatformClient` 只负责直接的平台 capability
    - 迁移期消息桥接由独立迁移入口承接，不放进原生客户端
    - 富消息链通过 `platform.send_chain` 发送，链构建能力位于专门的消息模块
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from ..message_components import BaseMessageComponent, Plain
from ..message_result import MessageChain
from ..message_session import MessageSession
from ..protocol.descriptors import SessionRef
from ._proxy import CapabilityProxy


class _PlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlatformStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"

    @classmethod
    def from_value(cls, value: Any) -> PlatformStatus:
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.PENDING


class PlatformError(_PlatformModel):
    message: str
    timestamp: str
    traceback: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> PlatformError | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class PlatformStats(_PlatformModel):
    id: str
    type: str
    display_name: str
    status: PlatformStatus
    started_at: str | None = None
    error_count: int
    last_error: PlatformError | None = None
    unified_webhook: bool
    meta: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> PlatformStats | None:
        if not isinstance(payload, dict):
            return None
        normalized = dict(payload)
        normalized["status"] = PlatformStatus.from_value(payload.get("status"))
        normalized["last_error"] = PlatformError.from_payload(
            payload.get("last_error") if isinstance(payload, dict) else None
        )
        meta = payload.get("meta")
        normalized["meta"] = dict(meta) if isinstance(meta, dict) else {}
        return cls.model_validate(normalized)


class PlatformClient:
    """平台消息客户端。

    提供向聊天平台发送消息和获取信息的能力。

    Attributes:
        _proxy: CapabilityProxy 实例，用于远程能力调用
    """

    def __init__(self, proxy: CapabilityProxy) -> None:
        """初始化平台客户端。

        Args:
            proxy: CapabilityProxy 实例
        """
        self._proxy = proxy

    def _build_target_payload(
        self,
        session: str | SessionRef | MessageSession,
    ) -> tuple[str, dict[str, Any]]:
        if isinstance(session, SessionRef):
            return session.session, {"target": session.to_payload()}
        if isinstance(session, MessageSession):
            return str(session), {}
        return str(session), {}

    async def _coerce_chain_payload(
        self,
        content: (
            str
            | MessageChain
            | Sequence[BaseMessageComponent]
            | Sequence[dict[str, Any]]
        ),
    ) -> list[dict[str, Any]]:
        if isinstance(content, str):
            return await MessageChain(
                [Plain(content, convert=False)]
            ).to_payload_async()
        if isinstance(content, MessageChain):
            return await content.to_payload_async()
        if (
            isinstance(content, Sequence)
            and not isinstance(content, (str, bytes))
            and all(isinstance(item, BaseMessageComponent) for item in content)
        ):
            components = cast(Sequence[BaseMessageComponent], content)
            return await MessageChain(list(components)).to_payload_async()
        if (
            isinstance(content, Sequence)
            and not isinstance(content, (str, bytes))
            and all(isinstance(item, dict) for item in content)
        ):
            payload_items = cast(Sequence[dict[str, Any]], content)
            return [dict(item) for item in payload_items]
        raise TypeError(
            "content must be str, MessageChain, sequence of message components, "
            "or sequence of platform.send_chain payload dicts"
        )

    async def send(
        self,
        session: str | SessionRef | MessageSession,
        text: str,
    ) -> dict[str, Any]:
        """发送文本消息。

        向指定的会话（用户或群组）发送文本消息。

        Args:
            session: 统一消息来源标识 (UMO)，格式如 "platform:instance:user_id"
            text: 要发送的文本内容

        Returns:
            发送结果，可能包含消息 ID 等信息

        示例:
            # 发送消息到当前会话
            await ctx.platform.send(event.session_id, "收到您的消息！")
        """
        session_id, extra = self._build_target_payload(session)
        return await self._proxy.call(
            "platform.send",
            {"session": session_id, "text": text, **extra},
        )

    async def send_image(
        self,
        session: str | SessionRef | MessageSession,
        image_url: str,
    ) -> dict[str, Any]:
        """发送图片消息。

        向指定的会话发送图片，支持 URL 或本地路径。

        Args:
            session: 统一消息来源标识 (UMO)
            image_url: 图片 URL 或本地文件路径

        Returns:
            发送结果

        示例:
            await ctx.platform.send_image(
                event.session_id,
                "https://example.com/image.png"
            )
        """
        session_id, extra = self._build_target_payload(session)
        return await self._proxy.call(
            "platform.send_image",
            {"session": session_id, "image_url": image_url, **extra},
        )

    async def send_chain(
        self,
        session: str | SessionRef | MessageSession,
        chain: MessageChain | Sequence[BaseMessageComponent] | Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        """发送富消息链。

        Args:
            session: 统一消息来源标识 (UMO)
            chain: 序列化后的消息组件数组

        Returns:
            发送结果
        """
        session_id, extra = self._build_target_payload(session)
        chain_payload = await self._coerce_chain_payload(chain)
        return await self._proxy.call(
            "platform.send_chain",
            {"session": session_id, "chain": chain_payload, **extra},
        )

    async def send_by_session(
        self,
        session: str | MessageSession,
        content: (
            str
            | MessageChain
            | Sequence[BaseMessageComponent]
            | Sequence[dict[str, Any]]
        ),
    ) -> dict[str, Any]:
        """主动向指定会话发送消息链。

        `Sequence[dict]` 的结构与 `platform.send_chain` 完全一致：
        每一项都应是 `{"type": "...", "data": {...}}`。
        """
        chain_payload = await self._coerce_chain_payload(content)
        session_id = str(session)
        return await self._proxy.call(
            "platform.send_by_session",
            {"session": session_id, "chain": chain_payload},
        )

    async def send_by_id(
        self,
        platform_id: str,
        session_id: str,
        content: (
            str
            | MessageChain
            | Sequence[BaseMessageComponent]
            | Sequence[dict[str, Any]]
        ),
        *,
        message_type: str = "private",
    ) -> dict[str, Any]:
        """主动向指定平台会话发送消息。"""
        session = MessageSession(
            platform_id=str(platform_id),
            message_type=str(message_type),
            session_id=str(session_id),
        )
        return await self.send_by_session(session, content)

    async def get_members(
        self,
        session: str | SessionRef | MessageSession,
    ) -> list[dict[str, Any]]:
        """获取群组成员列表。

        获取指定群组的成员信息列表。注意仅对群组会话有效。

        Args:
            session: 群组会话的统一消息来源标识 (UMO)

        Returns:
            成员信息列表，每个成员是一个字典，可能包含：
            - user_id: 用户 ID
            - nickname: 昵称
            - role: 角色 (owner, admin, member)

        示例:
            members = await ctx.platform.get_members(event.session_id)
            for member in members:
                print(f"{member['nickname']} ({member['user_id']})")
        """
        session_id, extra = self._build_target_payload(session)
        output = await self._proxy.call(
            "platform.get_members",
            {"session": session_id, **extra},
        )
        members = output.get("members")
        if not isinstance(members, (list, tuple)):
            return []
        return list(members)


__all__ = [
    "PlatformClient",
    "PlatformError",
    "PlatformStats",
    "PlatformStatus",
]
