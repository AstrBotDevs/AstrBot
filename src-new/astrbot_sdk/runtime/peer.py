from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from ..context import CancelToken
from ..errors import AstrBotError
from ..protocol.messages import (
    CancelMessage,
    ErrorPayload,
    EventMessage,
    InitializeMessage,
    InitializeOutput,
    InvokeMessage,
    PeerInfo,
    ResultMessage,
    parse_message,
)
from .capability_router import StreamExecution

InitializeHandler = Callable[[InitializeMessage], Awaitable[InitializeOutput]]
InvokeHandler = Callable[
    [InvokeMessage, CancelToken], Awaitable[dict[str, Any] | StreamExecution]
]
CancelHandler = Callable[[str], Awaitable[None]]


class Peer:
    """表示协议连接中的一个对等端。

    `Peer` 封装一条双向传输通道上的消息收发、初始化握手、能力调用、
    流式事件转发与取消处理。这里的 `peer` 指“通信对端/本端”这一网络
    协议概念，而不是业务上的用户、群聊或会话对象。
    """

    def __init__(
        self,
        *,
        transport,
        peer_info: PeerInfo,
        protocol_version: str = "1.0",
    ) -> None:
        """创建一个协议对等端实例。

        Args:
            transport: 底层传输实现，负责发送字符串消息并回调入站消息。
            peer_info: 当前端点对外声明的身份信息。
            protocol_version: 当前端点支持的协议版本，用于初始化握手校验。
        """
        self.transport = transport
        self.peer_info = peer_info
        self.protocol_version = protocol_version
        self.remote_peer: PeerInfo | None = None
        self.remote_handlers = []
        self.remote_capabilities = []
        self.remote_capability_map: dict[str, Any] = {}
        self.remote_metadata: dict[str, Any] = {}

        self._initialize_handler: InitializeHandler | None = None
        self._invoke_handler: InvokeHandler | None = None
        self._cancel_handler: CancelHandler | None = None
        self._counter = 0
        self._closed = False
        self._unusable = False
        self._pending_results: dict[str, asyncio.Future[ResultMessage]] = {}
        self._pending_streams: dict[str, asyncio.Queue[Any]] = {}
        self._inbound_tasks: dict[
            str, tuple[asyncio.Task[None], CancelToken, asyncio.Event]
        ] = {}
        self._remote_initialized = asyncio.Event()

    def set_initialize_handler(self, handler: InitializeHandler) -> None:
        """注册处理远端 `initialize` 请求的握手处理器。"""
        self._initialize_handler = handler

    def set_invoke_handler(self, handler: InvokeHandler) -> None:
        """注册处理远端 `invoke` 请求的能力调用处理器。"""
        self._invoke_handler = handler

    def set_cancel_handler(self, handler: CancelHandler) -> None:
        """注册处理远端 `cancel` 请求的取消回调。"""
        self._cancel_handler = handler

    async def start(self) -> None:
        """启动传输层并将原始入站消息绑定到当前 `Peer`。"""
        self.transport.set_message_handler(self._handle_raw_message)
        await self.transport.start()

    async def stop(self) -> None:
        """关闭 `Peer` 并清理所有挂起中的请求、流和入站任务。"""
        self._closed = True
        # 终止所有挂起的 RPC，避免调用方永久挂起
        for future in list(self._pending_results.values()):
            if not future.done():
                future.set_exception(AstrBotError.internal_error("连接已关闭"))
        self._pending_results.clear()

        for queue in list(self._pending_streams.values()):
            await queue.put(AstrBotError.internal_error("连接已关闭"))
        self._pending_streams.clear()

        # 取消所有入站任务
        for task, token, _started in list(self._inbound_tasks.values()):
            token.cancel()
            task.cancel()
        self._inbound_tasks.clear()

        await self.transport.stop()

    async def wait_closed(self) -> None:
        """等待底层传输彻底关闭。"""
        await self.transport.wait_closed()

    async def wait_until_remote_initialized(self, timeout: float | None = 30.0) -> None:
        """等待远端完成初始化握手。

        Args:
            timeout: 等待秒数。传入 `None` 表示无限等待。
        """
        if timeout is None:
            await self._remote_initialized.wait()
            return
        await asyncio.wait_for(self._remote_initialized.wait(), timeout=timeout)

    async def initialize(
        self,
        handlers,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> InitializeOutput:
        """向远端发送初始化请求并缓存远端声明的能力信息。

        Args:
            handlers: 当前端点声明可接收的处理器列表。
            metadata: 附带给远端的握手元数据。

        Returns:
            远端返回的初始化结果。
        """
        self._ensure_usable()
        request_id = self._next_id()
        future: asyncio.Future[ResultMessage] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_results[request_id] = future
        await self._send(
            InitializeMessage(
                id=request_id,
                protocol_version=self.protocol_version,
                peer=self.peer_info,
                handlers=list(handlers),
                metadata=metadata or {},
            )
        )
        result = await future
        if result.kind != "initialize_result":
            raise AstrBotError.protocol_error("initialize 必须收到 initialize_result")
        if not result.success:
            self._unusable = True
            await self.stop()
            raise AstrBotError.from_payload(
                result.error.model_dump() if result.error else {}
            )
        output = InitializeOutput.model_validate(result.output)
        self.remote_peer = output.peer
        self.remote_capabilities = output.capabilities
        self.remote_capability_map = {item.name: item for item in output.capabilities}
        self.remote_metadata = output.metadata
        return output

    async def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        stream: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """发起一次非流式能力调用并等待最终结果。

        Args:
            capability: 远端能力名。
            payload: 调用输入。
            stream: 必须为 `False`；流式场景应改用 `invoke_stream()`。
            request_id: 可选的请求 ID；未提供时自动生成。
        """
        self._ensure_usable()
        if stream:
            raise ValueError("stream=True 请使用 invoke_stream()")
        request_id = request_id or self._next_id()
        future: asyncio.Future[ResultMessage] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_results[request_id] = future
        await self._send(
            InvokeMessage(
                id=request_id,
                capability=capability,
                input=payload,
                stream=False,
            )
        )
        result = await future
        if not result.success:
            raise AstrBotError.from_payload(
                result.error.model_dump() if result.error else {}
            )
        return result.output

    async def invoke_stream(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[EventMessage]:
        """发起一次流式能力调用并返回事件迭代器。

        调用方会收到 `delta` 事件，`started` 会被内部吞掉，
        `completed` 用于结束迭代，`failed` 会转换为异常抛出。

        Args:
            capability: 远端能力名。
            payload: 调用输入。
            request_id: 可选的请求 ID；未提供时自动生成。
        """
        self._ensure_usable()
        request_id = request_id or self._next_id()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._pending_streams[request_id] = queue
        await self._send(
            InvokeMessage(
                id=request_id,
                capability=capability,
                input=payload,
                stream=True,
            )
        )

        async def iterator() -> AsyncIterator[EventMessage]:
            try:
                while True:
                    item = await queue.get()
                    if isinstance(item, Exception):
                        raise item
                    if not isinstance(item, EventMessage):
                        raise AstrBotError.protocol_error("流式调用收到非法事件")
                    if item.phase == "started":
                        continue
                    if item.phase == "delta":
                        yield item
                        continue
                    if item.phase == "completed":
                        break
                    if item.phase == "failed":
                        raise AstrBotError.from_payload(
                            item.error.model_dump() if item.error else {}
                        )
            finally:
                self._pending_streams.pop(request_id, None)

        return iterator()

    async def cancel(self, request_id: str, reason: str = "user_cancelled") -> None:
        """向远端发送取消请求，尝试中止指定 ID 的在途调用。"""
        await self._send(CancelMessage(id=request_id, reason=reason))

    def _next_id(self) -> str:
        """生成当前连接内递增的消息 ID。"""
        self._counter += 1
        return f"msg_{self._counter:04d}"

    def _ensure_usable(self) -> None:
        """确保连接仍处于可用状态，否则立即抛出协议错误。"""
        if self._unusable:
            raise AstrBotError.protocol_error("连接已进入不可用状态")

    async def _handle_raw_message(self, payload: str) -> None:
        """解析原始消息并分发到对应的消息处理分支。"""
        message = parse_message(payload)
        if isinstance(message, ResultMessage):
            await self._handle_result(message)
            return
        if isinstance(message, EventMessage):
            await self._handle_event(message)
            return
        if isinstance(message, InitializeMessage):
            await self._handle_initialize(message)
            return
        if isinstance(message, InvokeMessage):
            token = CancelToken()
            started = asyncio.Event()
            task = asyncio.create_task(self._handle_invoke(message, token, started))
            self._inbound_tasks[message.id] = (task, token, started)
            task.add_done_callback(
                lambda _task, request_id=message.id: self._inbound_tasks.pop(
                    request_id, None
                )
            )
            return
        if isinstance(message, CancelMessage):
            await self._handle_cancel(message)
            return

    async def _handle_initialize(self, message: InitializeMessage) -> None:
        """处理远端发起的初始化握手并返回握手结果。"""
        self.remote_peer = message.peer
        self.remote_handlers = message.handlers
        self.remote_metadata = message.metadata
        if self._initialize_handler is None:
            await self._reject_initialize(
                message,
                AstrBotError.protocol_error("对端不接受 initialize"),
            )
            return

        if message.protocol_version != self.protocol_version:
            await self._reject_initialize(
                message,
                AstrBotError.protocol_version_mismatch(
                    f"服务端支持协议版本 {self.protocol_version}，客户端请求版本 {message.protocol_version}"
                ),
            )
            return

        output = await self._initialize_handler(message)
        await self._send(
            ResultMessage(
                id=message.id,
                kind="initialize_result",
                success=True,
                output=output.model_dump(),
            )
        )
        self._remote_initialized.set()

    async def _handle_invoke(
        self,
        message: InvokeMessage,
        token: CancelToken,
        started: asyncio.Event,
    ) -> None:
        """处理远端发起的能力调用，并按流式或非流式协议返回结果。"""
        try:
            started.set()
            token.raise_if_cancelled()
            if self._invoke_handler is None:
                raise AstrBotError.capability_not_found(message.capability)
            execution = await self._invoke_handler(message, token)
            if message.stream:
                if not isinstance(execution, StreamExecution):
                    raise AstrBotError.protocol_error(
                        "stream=true 必须返回 StreamExecution"
                    )
                await self._send(EventMessage(id=message.id, phase="started"))
                chunks: list[dict[str, Any]] = []
                async for chunk in execution.iterator:
                    chunks.append(chunk)
                    await self._send(
                        EventMessage(id=message.id, phase="delta", data=chunk)
                    )
                await self._send(
                    EventMessage(
                        id=message.id,
                        phase="completed",
                        output=execution.finalize(chunks),
                    )
                )
                return
            if isinstance(execution, StreamExecution):
                raise AstrBotError.protocol_error("stream=false 不能返回流式执行对象")
            await self._send(
                ResultMessage(id=message.id, success=True, output=execution)
            )
        except asyncio.CancelledError:
            await self._send_cancelled_termination(message)
        except LookupError as exc:
            error = AstrBotError.invalid_input(str(exc))
            await self._send_error_result(message, error)
        except AstrBotError as exc:
            await self._send_error_result(message, exc)
        except Exception as exc:
            await self._send_error_result(
                message, AstrBotError.internal_error(str(exc))
            )

    async def _handle_cancel(self, message: CancelMessage) -> None:
        """处理远端取消请求并终止对应的入站任务。"""
        inbound = self._inbound_tasks.get(message.id)
        if inbound is None:
            return
        task, token, started = inbound
        token.cancel()
        if self._cancel_handler is not None:
            await self._cancel_handler(message.id)
        if started.is_set():
            task.cancel()

    async def _handle_result(self, message: ResultMessage) -> None:
        """处理非流式结果消息并唤醒等待中的调用方。"""
        future = self._pending_results.pop(message.id, None)
        if future is None:
            queue = self._pending_streams.get(message.id)
            if queue is not None:
                await queue.put(
                    AstrBotError.protocol_error("stream=true 调用不应收到 result")
                )
            return
        # 检查 future 是否已完成（可能被调用方取消）
        if not future.done():
            future.set_result(message)

    async def _handle_event(self, message: EventMessage) -> None:
        """处理流式事件消息并投递到对应请求的事件队列。"""
        queue = self._pending_streams.get(message.id)
        if queue is None:
            future = self._pending_results.get(message.id)
            if future is not None and not future.done():
                future.set_exception(
                    AstrBotError.protocol_error("stream=false 调用不应收到 event")
                )
            return
        await queue.put(message)

    async def _send_error_result(
        self, message: InvokeMessage, error: AstrBotError
    ) -> None:
        """根据调用模式，将错误编码为 `result` 或失败事件发回远端。"""
        if message.stream:
            await self._send(
                EventMessage(
                    id=message.id,
                    phase="failed",
                    error=ErrorPayload.model_validate(error.to_payload()),
                )
            )
            return
        await self._send(
            ResultMessage(
                id=message.id,
                success=False,
                error=ErrorPayload.model_validate(error.to_payload()),
            )
        )

    async def _reject_initialize(
        self, message: InitializeMessage, error: AstrBotError
    ) -> None:
        """拒绝一次初始化握手，并把连接标记为不可继续使用。"""
        await self._send(
            ResultMessage(
                id=message.id,
                kind="initialize_result",
                success=False,
                error=ErrorPayload.model_validate(error.to_payload()),
            )
        )
        self._unusable = True
        self._remote_initialized.set()
        await self.stop()

    async def _send_cancelled_termination(self, message: InvokeMessage) -> None:
        """把本端取消执行转换为标准化的取消错误响应。"""
        error = AstrBotError.cancelled()
        await self._send_error_result(message, error)

    async def _send(self, message) -> None:
        """序列化协议消息并通过底层传输发送出去。"""
        await self.transport.send(message.model_dump_json(exclude_none=True))
