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
InvokeHandler = Callable[[InvokeMessage, CancelToken], Awaitable[dict[str, Any] | StreamExecution]]
CancelHandler = Callable[[str], Awaitable[None]]


class Peer:
    def __init__(
        self,
        *,
        transport,
        peer_info: PeerInfo,
        protocol_version: str = "1.0",
    ) -> None:
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
        self._inbound_tasks: dict[str, tuple[asyncio.Task[None], CancelToken]] = {}
        self._remote_initialized = asyncio.Event()

    def set_initialize_handler(self, handler: InitializeHandler) -> None:
        self._initialize_handler = handler

    def set_invoke_handler(self, handler: InvokeHandler) -> None:
        self._invoke_handler = handler

    def set_cancel_handler(self, handler: CancelHandler) -> None:
        self._cancel_handler = handler

    async def start(self) -> None:
        self.transport.set_message_handler(self._handle_raw_message)
        await self.transport.start()

    async def stop(self) -> None:
        self._closed = True
        await self.transport.stop()

    async def wait_closed(self) -> None:
        await self.transport.wait_closed()

    async def wait_until_remote_initialized(self, timeout: float | None = 30.0) -> None:
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
        self._ensure_usable()
        request_id = self._next_id()
        future: asyncio.Future[ResultMessage] = asyncio.get_running_loop().create_future()
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
            raise AstrBotError.from_payload(result.error.model_dump() if result.error else {})
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
        self._ensure_usable()
        if stream:
            raise ValueError("stream=True 请使用 invoke_stream()")
        request_id = request_id or self._next_id()
        future: asyncio.Future[ResultMessage] = asyncio.get_running_loop().create_future()
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
            raise AstrBotError.from_payload(result.error.model_dump() if result.error else {})
        return result.output

    async def invoke_stream(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[EventMessage]:
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
                        raise AstrBotError.from_payload(item.error.model_dump() if item.error else {})
            finally:
                self._pending_streams.pop(request_id, None)

        return iterator()

    async def cancel(self, request_id: str, reason: str = "user_cancelled") -> None:
        await self._send(CancelMessage(id=request_id, reason=reason))

    def _next_id(self) -> str:
        self._counter += 1
        return f"msg_{self._counter:04d}"

    def _ensure_usable(self) -> None:
        if self._unusable:
            raise AstrBotError.protocol_error("连接已进入不可用状态")

    async def _handle_raw_message(self, payload: str) -> None:
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
            task = asyncio.create_task(self._handle_invoke(message))
            token = CancelToken()
            self._inbound_tasks[message.id] = (task, token)
            task.add_done_callback(lambda _task, request_id=message.id: self._inbound_tasks.pop(request_id, None))
            return
        if isinstance(message, CancelMessage):
            await self._handle_cancel(message)
            return

    async def _handle_initialize(self, message: InitializeMessage) -> None:
        self.remote_peer = message.peer
        self.remote_handlers = message.handlers
        self.remote_metadata = message.metadata
        if self._initialize_handler is None:
            error = AstrBotError.protocol_error("对端不接受 initialize")
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
            return

        if message.protocol_version != self.protocol_version:
            error = AstrBotError.protocol_version_mismatch(
                f"服务端支持协议版本 {self.protocol_version}，客户端请求版本 {message.protocol_version}"
            )
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

    async def _handle_invoke(self, message: InvokeMessage) -> None:
        active = self._inbound_tasks.get(message.id)
        token = active[1] if active is not None else CancelToken()
        try:
            if self._invoke_handler is None:
                raise AstrBotError.capability_not_found(message.capability)
            execution = await self._invoke_handler(message, token)
            if message.stream:
                if not isinstance(execution, StreamExecution):
                    raise AstrBotError.protocol_error("stream=true 必须返回 StreamExecution")
                await self._send(EventMessage(id=message.id, phase="started"))
                chunks: list[dict[str, Any]] = []
                async for chunk in execution.iterator:
                    chunks.append(chunk)
                    await self._send(EventMessage(id=message.id, phase="delta", data=chunk))
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
            await self._send(ResultMessage(id=message.id, success=True, output=execution))
        except asyncio.CancelledError:
            await self._send_cancelled_termination(message)
        except LookupError as exc:
            error = AstrBotError.invalid_input(str(exc))
            await self._send_error_result(message, error)
        except AstrBotError as exc:
            await self._send_error_result(message, exc)
        except Exception as exc:
            await self._send_error_result(message, AstrBotError.internal_error(str(exc)))

    async def _handle_cancel(self, message: CancelMessage) -> None:
        inbound = self._inbound_tasks.get(message.id)
        if inbound is None:
            return
        task, token = inbound
        token.cancel()
        if self._cancel_handler is not None:
            await self._cancel_handler(message.id)
        task.cancel()

    async def _handle_result(self, message: ResultMessage) -> None:
        future = self._pending_results.pop(message.id, None)
        if future is None:
            queue = self._pending_streams.get(message.id)
            if queue is not None:
                await queue.put(AstrBotError.protocol_error("stream=true 调用不应收到 result"))
            return
        future.set_result(message)

    async def _handle_event(self, message: EventMessage) -> None:
        queue = self._pending_streams.get(message.id)
        if queue is None:
            future = self._pending_results.get(message.id)
            if future is not None:
                future.set_exception(AstrBotError.protocol_error("stream=false 调用不应收到 event"))
            return
        await queue.put(message)

    async def _send_error_result(self, message: InvokeMessage, error: AstrBotError) -> None:
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

    async def _send_cancelled_termination(self, message: InvokeMessage) -> None:
        error = AstrBotError.cancelled()
        await self._send_error_result(message, error)

    async def _send(self, message) -> None:
        await self.transport.send(message.model_dump_json(exclude_none=True))
