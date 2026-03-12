"""能力代理模块。

提供 CapabilityProxy 类，作为客户端与 Peer 之间的中间层，负责：
- 检查远程能力是否可用
- 验证流式调用支持
- 统一封装 invoke 和 invoke_stream 调用

设计说明：
    CapabilityProxy 是新版架构的核心组件，实现了从旧版 Context 直接方法调用
    到新版 RPC 能力调用的转换。每个专用客户端 (LLMClient, DBClient 等)
    都通过 CapabilityProxy 与远程通信。

    旧版设计:
        Context.llm_generate() → 直接调用内部方法

    新版设计:
        LLMClient.chat() → CapabilityProxy.call() → Peer.invoke() → RPC 通信

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
    ) -> dict[str, Any]: ...

    async def invoke_stream(
        self,
        capability: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[Any]: ...


class CapabilityProxy:
    """能力代理类，封装 Peer 的能力调用接口。

    负责在调用前验证能力可用性和流式支持，提供统一的 call/stream 接口。

    Attributes:
        _peer: 底层 Peer 实例，负责实际的 RPC 通信
    """

    def __init__(self, peer: _CapabilityPeerLike) -> None:
        """初始化能力代理。

        Args:
            peer: Peer 实例，提供 remote_capability_map 和 invoke/invoke_stream 方法
        """
        self._peer = peer

    def _get_descriptor(self, name: str):
        """获取能力描述符。

        Args:
            name: 能力名称，如 "llm.chat"

        Returns:
            能力描述符，若不存在则返回 None
        """
        capability_map = getattr(self._peer, "__dict__", {}).get(
            "remote_capability_map",
            {},
        )
        return capability_map.get(name)

    def _remote_initialized(self) -> bool:
        peer_state = getattr(self._peer, "__dict__", {})
        return bool(peer_state.get("remote_peer")) or bool(
            peer_state.get("remote_capability_map", {})
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
        return await self._peer.invoke(name, payload, stream=False)

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
        event_stream = await self._peer.invoke_stream(name, payload)
        async for event in event_stream:
            if event.phase == "delta":
                yield event.data
