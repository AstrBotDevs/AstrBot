from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from astrbot_sdk.errors import AstrBotError, ErrorCodes
from astrbot_sdk.protocol.messages import (
    EventMessage,
    PeerInfo,
    ResultMessage,
    parse_message,
)
from astrbot_sdk.runtime.peer import Peer
from astrbot_sdk.runtime.transport import Transport


class _ControlledTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.sent_payloads: list[str] = []
        self.on_send: Callable[[str], Awaitable[None]] | None = None

    async def start(self) -> None:
        self._closed.clear()

    async def stop(self) -> None:
        self._closed.set()

    async def send(self, payload: str) -> None:
        self.sent_payloads.append(payload)
        if self.on_send is not None:
            await self.on_send(payload)

    async def push_message(self, message: Any) -> None:
        if isinstance(message, str):
            payload = message
        else:
            payload = message.model_dump_json(exclude_none=True)
        await self._dispatch(payload)

    def close_unexpected(self) -> None:
        self._closed.set()


def _make_peer(transport: _ControlledTransport, *, name: str = "test-plugin") -> Peer:
    return Peer(
        transport=transport,
        peer_info=PeerInfo(name=name, role="plugin", version="v4"),
    )


async def _stop_peer(peer: Peer) -> None:
    await peer.stop()
    if peer._transport_watch_task is not None:
        await peer._transport_watch_task


@pytest.mark.asyncio
async def test_initialize_marks_remote_initialized_on_active_side() -> None:
    transport = _ControlledTransport()
    peer = _make_peer(transport)

    async def respond_to_initialize(payload: str) -> None:
        message = parse_message(payload)
        assert message.type == "initialize"
        await transport.push_message(
            ResultMessage(
                id=message.id,
                kind="initialize_result",
                success=True,
                output={
                    "peer": {
                        "name": "astrbot-core",
                        "role": "core",
                        "version": "v4",
                    },
                    "protocol_version": "1.0",
                    "capabilities": [],
                    "metadata": {"mode": "test"},
                },
            )
        )

    transport.on_send = respond_to_initialize
    await peer.start()
    try:
        waiter = asyncio.create_task(peer.wait_until_remote_initialized(timeout=0.2))
        await asyncio.sleep(0)
        assert not waiter.done()

        output = await peer.initialize([])
        await waiter

        assert output.peer.name == "astrbot-core"
        assert peer.remote_peer is not None
        assert peer.remote_peer.name == "astrbot-core"
        assert peer.remote_metadata["mode"] == "test"
    finally:
        await _stop_peer(peer)


@pytest.mark.asyncio
async def test_wait_until_remote_initialized_fails_when_transport_closes_pre_init() -> (
    None
):
    transport = _ControlledTransport()
    peer = _make_peer(transport)
    await peer.start()
    try:
        waiter = asyncio.create_task(peer.wait_until_remote_initialized(timeout=None))
        await asyncio.sleep(0)

        transport.close_unexpected()

        with pytest.raises(AstrBotError, match="连接在初始化完成前关闭") as exc_info:
            await asyncio.wait_for(waiter, timeout=0.2)

        assert exc_info.value.code == ErrorCodes.PROTOCOL_ERROR
    finally:
        await _stop_peer(peer)


@pytest.mark.asyncio
async def test_invoke_fails_pending_call_on_unexpected_transport_close() -> None:
    transport = _ControlledTransport()
    peer = _make_peer(transport)
    await peer.start()
    try:
        invoke_task = asyncio.create_task(peer.invoke("llm.chat", {"prompt": "hello"}))
        await asyncio.sleep(0)

        assert len(transport.sent_payloads) == 1
        transport.close_unexpected()

        with pytest.raises(AstrBotError, match="连接已关闭") as exc_info:
            await asyncio.wait_for(invoke_task, timeout=0.2)

        assert exc_info.value.code == ErrorCodes.NETWORK_ERROR
    finally:
        await _stop_peer(peer)


@pytest.mark.asyncio
async def test_invoke_stream_fails_pending_iterator_on_unexpected_transport_close() -> (
    None
):
    transport = _ControlledTransport()
    peer = _make_peer(transport)
    await peer.start()
    try:
        iterator = await peer.invoke_stream("llm.stream", {"prompt": "hello"})
        consume_task = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0)

        assert len(transport.sent_payloads) == 1
        transport.close_unexpected()

        with pytest.raises(AstrBotError, match="连接已关闭") as exc_info:
            await asyncio.wait_for(consume_task, timeout=0.2)

        assert exc_info.value.code == ErrorCodes.NETWORK_ERROR
    finally:
        await _stop_peer(peer)


@pytest.mark.asyncio
async def test_invoke_stream_hides_completed_event_by_default() -> None:
    transport = _ControlledTransport()
    peer = _make_peer(transport)

    async def emit_stream(payload: str) -> None:
        message = parse_message(payload)
        assert message.type == "invoke"
        await transport.push_message(EventMessage(id=message.id, phase="started"))
        await transport.push_message(
            EventMessage(id=message.id, phase="delta", data={"text": "hello"})
        )
        await transport.push_message(
            EventMessage(id=message.id, phase="completed", output={"text": "hello"})
        )

    transport.on_send = emit_stream
    await peer.start()
    try:
        iterator = await peer.invoke_stream("llm.stream", {"prompt": "hello"})
        events = [event async for event in iterator]

        assert [(event.phase, event.data, event.output) for event in events] == [
            ("delta", {"text": "hello"}, {})
        ]
    finally:
        await _stop_peer(peer)


@pytest.mark.asyncio
async def test_invoke_stream_can_include_completed_event() -> None:
    transport = _ControlledTransport()
    peer = _make_peer(transport)

    async def emit_stream(payload: str) -> None:
        message = parse_message(payload)
        assert message.type == "invoke"
        await transport.push_message(EventMessage(id=message.id, phase="started"))
        await transport.push_message(
            EventMessage(id=message.id, phase="delta", data={"text": "hello"})
        )
        await transport.push_message(
            EventMessage(id=message.id, phase="completed", output={"text": "hello"})
        )

    transport.on_send = emit_stream
    await peer.start()
    try:
        iterator = await peer.invoke_stream(
            "llm.stream",
            {"prompt": "hello"},
            include_completed=True,
        )
        events = [event async for event in iterator]

        assert [(event.phase, event.data, event.output) for event in events] == [
            ("delta", {"text": "hello"}, {}),
            ("completed", {}, {"text": "hello"}),
        ]
    finally:
        await _stop_peer(peer)


@pytest.mark.asyncio
async def test_invoke_stream_failed_event_becomes_exception() -> None:
    transport = _ControlledTransport()
    peer = _make_peer(transport)

    async def emit_failed_event(payload: str) -> None:
        message = parse_message(payload)
        assert message.type == "invoke"
        await transport.push_message(EventMessage(id=message.id, phase="started"))
        await transport.push_message(
            EventMessage(
                id=message.id,
                phase="failed",
                error={
                    "code": ErrorCodes.INTERNAL_ERROR,
                    "message": "boom",
                    "hint": "",
                    "retryable": False,
                    "docs_url": "",
                },
            )
        )

    transport.on_send = emit_failed_event
    await peer.start()
    try:
        iterator = await peer.invoke_stream("llm.stream", {"prompt": "hello"})

        with pytest.raises(AstrBotError, match="boom") as exc_info:
            async for _event in iterator:
                pass

        assert exc_info.value.code == ErrorCodes.INTERNAL_ERROR
    finally:
        await _stop_peer(peer)
