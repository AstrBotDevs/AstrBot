"""能力代理模块。

提供 CapabilityProxy 类，作为客户端与 Peer 之间的中间层，负责：
- 检查远程能力是否可用
- 验证流式调用支持
- 统一封装 invoke 和 invoke_stream 调用

设计说明：
    CapabilityProxy 是新版架构的核心组件。每个专用客户端 (LLMClient, DBClient 等)
    都通过 CapabilityProxy 与远程通信，并在发起调用时绑定当前插件身份，
    让运行时把调用者信息放进协议层而不是业务 payload。

使用示例:
    proxy = CapabilityProxy(peer)

    # 普通调用
    result = await proxy.call("llm.chat", {"prompt": "hello"})

    # 流式调用
    async for delta in proxy.stream("llm.stream_chat", {"prompt": "hello"}):
        print(delta["text"])
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol

from .._internal.invocation_context import caller_plugin_scope
from ..errors import AstrBotError


class _CapabilityDescriptorLike(Protocol):
    supports_stream: bool | None


class _CapabilityPeerLike(Protocol):
    remote_capability_map: Mapping[str, _CapabilityDescriptorLike]
    remote_peer: Any | None

    async def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        stream: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def invoke_stream(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[Any]: ...


class CapabilityProxy:
    """能力代理类，封装 Peer 的能力调用接口。

    负责在调用前验证能力可用性和流式支持，提供统一的 call/stream 接口。

    Attributes:
        _peer: 底层 Peer 实例，负责实际的 RPC 通信
    """

    def __init__(
        self,
        peer: _CapabilityPeerLike,
        caller_plugin_id: str | None = None,
        request_scope_id: str | None = None,
    ) -> None:
        """初始化能力代理。

        Args:
            peer: Peer 实例，提供 remote_capability_map 和 invoke/invoke_stream 方法
        """
        self._peer = peer
        self._caller_plugin_id = caller_plugin_id
        self._request_scope_id = request_scope_id

    def _get_descriptor(self, name: str):
        """获取能力描述符。

        Args:
            name: 能力名称，如 "llm.chat"

        Returns:
            能力描述符，若不存在则返回 None
        """
        capability_map = getattr(self._peer, "remote_capability_map", {})
        if not isinstance(capability_map, Mapping):
            return None
        return capability_map.get(name)

    def _remote_initialized(self) -> bool:
        peer_attrs = getattr(self._peer, "__dict__", None)
        if not isinstance(peer_attrs, dict):
            return False

        # Avoid getattr() here: MagicMock synthesizes truthy child attributes and
        # makes an uninitialized peer look ready.
        remote_peer = peer_attrs.get("remote_peer")
        capability_map = peer_attrs.get("remote_capability_map")
        return bool(remote_peer) or (
            isinstance(capability_map, Mapping) and bool(capability_map)
        )

    def _ensure_available(self, name: str, *, stream: bool) -> None:
        """确保能力可用且支持指定的调用模式。

        Args:
            name: 能力名称
            stream: 是否需要流式支持

        Raises:
            AstrBotError: 能力不存在或流式不支持
        """
        descriptor = self._get_descriptor(name)
        if descriptor is None:
            if self._remote_initialized():
                raise AstrBotError.capability_not_found(name)
            return
        if stream and not descriptor.supports_stream:
            raise AstrBotError.invalid_input(f"{name} 不支持 stream=true")

    def _prepare_payload(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if (
            not isinstance(self._request_scope_id, str)
            or not self._request_scope_id
            or not name.startswith("system.event.")
        ):
            return payload
        scoped_payload = dict(payload)
        scoped_payload.setdefault("_request_scope_id", self._request_scope_id)
        return scoped_payload

    async def call(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """执行普通能力调用（非流式）。

        Args:
            name: 能力名称，如 "llm.chat", "db.get"
            payload: 调用参数字典

        Returns:
            调用结果字典

        Raises:
            AstrBotError: 能力不存在或调用失败

        示例:
            result = await proxy.call("llm.chat", {"prompt": "hello"})
            print(result["text"])
        """
        self._ensure_available(name, stream=False)
        prepared_payload = self._prepare_payload(name, payload)
        with caller_plugin_scope(self._caller_plugin_id):
            return await self._peer.invoke(name, prepared_payload, stream=False)

    async def stream(
        self,
        name: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """执行流式能力调用。

        Args:
            name: 能力名称，如 "llm.stream_chat"
            payload: 调用参数字典

        Yields:
            每个增量数据块（phase="delta" 时的 data 字段）

        Raises:
            AstrBotError: 能力不存在或不支持流式

        示例:
            async for delta in proxy.stream("llm.stream_chat", {"prompt": "hello"}):
                print(delta["text"], end="")
        """
        self._ensure_available(name, stream=True)
        prepared_payload = self._prepare_payload(name, payload)
        with caller_plugin_scope(self._caller_plugin_id):
            event_stream = await self._peer.invoke_stream(name, prepared_payload)
        async for event in event_stream:
            if event.phase == "delta":
                yield event.data
