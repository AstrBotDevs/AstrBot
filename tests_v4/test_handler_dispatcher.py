"""
Tests for runtime/handler_dispatcher.py - HandlerDispatcher implementation.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.events import MessageEvent, PlainTextResult
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    HandlerDescriptor,
)
from astrbot_sdk.protocol.messages import InvokeMessage
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.runtime.loader import LoadedHandler


class MockPeer:
    """Mock peer for testing."""

    def __init__(self):
        self.sent_messages: list[dict[str, Any]] = []
        self.platform = self  # platform.send 通过 self.send 调用
        # CapabilityProxy 需要的属性
        self.remote_capability_map: dict[str, Any] = {}

    async def send(self, session_id: str, text: str) -> None:
        """模拟 platform.send 方法"""
        self.sent_messages.append({"session_id": session_id, "text": text})

    async def invoke(
        self, name: str, payload: dict[str, Any], stream: bool = False
    ) -> dict[str, Any]:
        """模拟 peer.invoke 方法，用于 CapabilityProxy"""
        if name == "platform.send":
            await self.send(payload.get("session_id", ""), payload.get("text", ""))
            return {}
        return {}


def create_mock_handler(
    handler_id: str = "test.handler",
    command: str = "hello",
) -> LoadedHandler:
    """Create a mock loaded handler."""
    descriptor = HandlerDescriptor(
        id=handler_id,
        trigger=CommandTrigger(command=command),
    )

    async def handler_func(event: MessageEvent, ctx: Context):
        await event.reply("Hello!")
        return None

    handler_func.__func__ = handler_func  # Simulate bound method

    return LoadedHandler(
        descriptor=descriptor,
        callable=handler_func,
        owner=MagicMock(),
        legacy_context=None,
    )


def create_invoke_message(
    message_id: str = "msg_001",
    handler_id: str = "test.handler",
    event_data: dict[str, Any] | None = None,
    args: dict[str, Any] | None = None,
) -> InvokeMessage:
    """Create a mock invoke message."""
    input_data = {"handler_id": handler_id, "event": event_data or {}}
    if args:
        input_data["args"] = args
    return InvokeMessage(
        id=message_id,
        capability="handler.invoke",
        input=input_data,
    )


def create_message_event() -> MessageEvent:
    """Create a mock message event."""
    return MessageEvent(
        session_id="session-1",
        user_id="user-1",
        platform="test",
        text="hello world",
    )


class TestHandlerDispatcherInit:
    """Tests for HandlerDispatcher initialization."""

    def test_init(self):
        """HandlerDispatcher should initialize with handlers."""
        peer = MockPeer()
        handler = create_mock_handler()

        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[handler],
        )

        assert dispatcher._plugin_id == "test_plugin"
        assert dispatcher._peer is peer
        assert "test.handler" in dispatcher._handlers
        assert dispatcher._active == {}

    def test_handlers_indexed_by_id(self):
        """HandlerDispatcher should index handlers by id."""
        peer = MockPeer()
        handlers = [
            create_mock_handler("handler.one", "cmd1"),
            create_mock_handler("handler.two", "cmd2"),
        ]

        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=handlers,
        )

        assert "handler.one" in dispatcher._handlers
        assert "handler.two" in dispatcher._handlers


class TestHandlerDispatcherInvoke:
    """Tests for HandlerDispatcher.invoke method."""

    @pytest.mark.asyncio
    async def test_invoke_calls_handler(self):
        """invoke should call the registered handler."""
        peer = MockPeer()
        sent_messages = []

        # 记录 platform.send 的调用
        original_send = peer.send

        async def track_send(session_id: str, text: str) -> None:
            sent_messages.append({"session_id": session_id, "text": text})
            await original_send(session_id, text)

        peer.send = track_send

        handler_called = []

        async def handler_func(e: MessageEvent, ctx: Context):
            handler_called.append(e)
            await e.reply("response")

        descriptor = HandlerDescriptor(
            id="test.handler",
            trigger=CommandTrigger(command="hello"),
        )
        handler = LoadedHandler(
            descriptor=descriptor,
            callable=handler_func,
            owner=MagicMock(),
            legacy_context=None,
        )

        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[handler],
        )

        event = create_message_event()
        # MessageEvent 使用 to_payload() 而不是 model_dump()
        message = InvokeMessage(
            id="msg_001",
            capability="handler.invoke",
            input={"handler_id": "test.handler", "event": event.to_payload()},
        )

        cancel_token = CancelToken()
        result = await dispatcher.invoke(message, cancel_token)

        assert result == {}
        assert len(handler_called) == 1
        # 验证 reply 通过 platform.send 发送
        assert any("response" in m.get("text", "") for m in sent_messages)

    @pytest.mark.asyncio
    async def test_invoke_missing_handler_raises(self):
        """invoke should raise LookupError for missing handler."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        message = InvokeMessage(
            id="msg_001",
            capability="handler.invoke",
            input={"handler_id": "nonexistent.handler", "event": {}},
        )

        cancel_token = CancelToken()

        with pytest.raises(LookupError, match="handler not found"):
            await dispatcher.invoke(message, cancel_token)

    @pytest.mark.asyncio
    async def test_invoke_with_legacy_args(self):
        """invoke should pass legacy args to handler."""
        peer = MockPeer()

        received_args = []

        async def handler_func(event: MessageEvent, ctx: Context, name: str):
            received_args.append(name)
            return None

        descriptor = HandlerDescriptor(
            id="test.handler",
            trigger=CommandTrigger(command="hello"),
        )
        handler = LoadedHandler(
            descriptor=descriptor,
            callable=handler_func,
            owner=MagicMock(),
            legacy_context=None,
        )

        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[handler],
        )

        message = InvokeMessage(
            id="msg_001",
            capability="handler.invoke",
            input={
                "handler_id": "test.handler",
                "event": {
                    "type": "message",
                    "session_id": "s1",
                    "user_id": "u1",
                    "platform": "test",
                },
                "args": {"name": "test_name"},
            },
        )

        cancel_token = CancelToken()
        await dispatcher.invoke(message, cancel_token)

        assert "test_name" in received_args

    @pytest.mark.asyncio
    async def test_invoke_tracks_active_task(self):
        """invoke should track active task."""
        peer = MockPeer()

        async def slow_handler(event: MessageEvent, ctx: Context):
            await asyncio.sleep(0.1)
            return None

        descriptor = HandlerDescriptor(
            id="slow.handler",
            trigger=CommandTrigger(command="slow"),
        )
        handler = LoadedHandler(
            descriptor=descriptor,
            callable=slow_handler,
            owner=MagicMock(),
            legacy_context=None,
        )

        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[handler],
        )

        message = InvokeMessage(
            id="msg_001",
            capability="handler.invoke",
            input={
                "handler_id": "slow.handler",
                "event": {
                    "type": "message",
                    "session_id": "s1",
                    "user_id": "u1",
                    "platform": "test",
                },
            },
        )

        cancel_token = CancelToken()

        # Start invoke in background
        task = asyncio.create_task(dispatcher.invoke(message, cancel_token))

        # Give it time to start
        await asyncio.sleep(0)

        # Should have active task during execution
        # Note: might be empty if task completes quickly

        await task

        # After completion, should be cleared
        assert "msg_001" not in dispatcher._active


class TestHandlerDispatcherCancel:
    """Tests for HandlerDispatcher.cancel method."""

    @pytest.mark.asyncio
    async def test_cancel_stops_active_task(self):
        """cancel should stop the active task."""
        peer = MockPeer()

        cancelled = []

        async def slow_handler(event: MessageEvent, ctx: Context):
            try:
                await asyncio.sleep(10)  # Long sleep
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        descriptor = HandlerDescriptor(
            id="slow.handler",
            trigger=CommandTrigger(command="slow"),
        )
        handler = LoadedHandler(
            descriptor=descriptor,
            callable=slow_handler,
            owner=MagicMock(),
            legacy_context=None,
        )

        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[handler],
        )

        message = InvokeMessage(
            id="msg_001",
            capability="handler.invoke",
            input={
                "handler_id": "slow.handler",
                "event": {
                    "type": "message",
                    "session_id": "s1",
                    "user_id": "u1",
                    "platform": "test",
                },
            },
        )

        cancel_token = CancelToken()

        # Start invoke
        task = asyncio.create_task(dispatcher.invoke(message, cancel_token))

        # Wait for task to be active
        await asyncio.sleep(0.05)

        # Cancel
        await dispatcher.cancel("msg_001")

        # Task should be cancelled
        await asyncio.sleep(0.05)

        assert cancelled or task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_cancel_unknown_request_does_nothing(self):
        """cancel should do nothing for unknown request."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        # Should not raise
        await dispatcher.cancel("unknown_request")


class TestHandlerDispatcherBuildArgs:
    """Tests for HandlerDispatcher._build_args method."""

    def test_build_args_event_parameter(self):
        """_build_args should inject event parameter."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        def handler(event: MessageEvent, ctx: Context):
            pass

        event = create_message_event()
        ctx = Context(peer=peer, plugin_id="test", cancel_token=CancelToken())

        args = dispatcher._build_args(handler, event, ctx)

        assert args[0] is event

    def test_build_args_ctx_parameter(self):
        """_build_args should inject ctx/context parameter."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        def handler(event: MessageEvent, ctx: Context):
            pass

        event = create_message_event()
        ctx = Context(peer=peer, plugin_id="test", cancel_token=CancelToken())

        args = dispatcher._build_args(handler, event, ctx)

        assert args[1] is ctx

    def test_build_args_legacy_args(self):
        """_build_args should inject legacy args."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        def handler(event: MessageEvent, ctx: Context, custom_arg: str):
            pass

        event = create_message_event()
        ctx = Context(peer=peer, plugin_id="test", cancel_token=CancelToken())

        args = dispatcher._build_args(handler, event, ctx, {"custom_arg": "value"})

        assert args[2] == "value"

    def test_build_args_skip_keyword_only(self):
        """_build_args should skip keyword-only parameters."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        def handler(event: MessageEvent, *, optional: str = "default"):
            pass

        event = create_message_event()
        ctx = Context(peer=peer, plugin_id="test", cancel_token=CancelToken())

        args = dispatcher._build_args(handler, event, ctx)

        # Should only have event
        assert len(args) == 1


class TestHandlerDispatcherConsumeResult:
    """Tests for HandlerDispatcher._consume_legacy_result method."""

    @pytest.mark.asyncio
    async def test_consume_plain_text_result(self):
        """_consume_legacy_result should handle PlainTextResult."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        replies = []
        event = create_message_event()

        # reply_handler 必须是异步的
        async def async_reply(text: str) -> None:
            replies.append(text)

        event._reply_handler = async_reply

        result = PlainTextResult(text="plain text")
        await dispatcher._consume_legacy_result(result, event)

        assert "plain text" in replies

    @pytest.mark.asyncio
    async def test_consume_string(self):
        """_consume_legacy_result should handle string."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        replies = []
        event = create_message_event()

        # reply_handler 必须是异步的
        async def async_reply(text: str) -> None:
            replies.append(text)

        event._reply_handler = async_reply

        await dispatcher._consume_legacy_result("string reply", event)

        assert "string reply" in replies

    @pytest.mark.asyncio
    async def test_consume_dict_with_text(self):
        """_consume_legacy_result should handle dict with text."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        replies = []
        event = create_message_event()

        # reply_handler 必须是异步的
        async def async_reply(text: str) -> None:
            replies.append(text)

        event._reply_handler = async_reply

        await dispatcher._consume_legacy_result({"text": "dict reply"}, event)

        assert "dict reply" in replies

    @pytest.mark.asyncio
    async def test_consume_other_type_ignored(self):
        """_consume_legacy_result should ignore other types."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        event = create_message_event()
        event._reply_handler = MagicMock()

        # Should not raise
        await dispatcher._consume_legacy_result(123, event)
        await dispatcher._consume_legacy_result(None, event)


class TestHandlerDispatcherHandleError:
    """Tests for HandlerDispatcher._handle_error method."""

    @pytest.mark.asyncio
    async def test_handle_error_with_on_error_method(self):
        """_handle_error should call owner.on_error if available."""
        peer = MockPeer()

        errors_handled = []

        class OwnerWithOnError:
            async def on_error(self, exc: Exception, event: MessageEvent, ctx: Context):
                errors_handled.append(exc)

        owner = OwnerWithOnError()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        event = create_message_event()
        ctx = Context(peer=peer, plugin_id="test", cancel_token=CancelToken())
        exc = ValueError("test error")

        await dispatcher._handle_error(owner, exc, event, ctx)

        assert exc in errors_handled

    @pytest.mark.asyncio
    async def test_handle_error_without_on_error_method(self):
        """_handle_error should use Star.on_error if owner has no on_error."""
        peer = MockPeer()
        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[],
        )

        event = create_message_event()
        ctx = Context(peer=peer, plugin_id="test", cancel_token=CancelToken())
        exc = ValueError("test error")

        # owner 是 MagicMock，on_error 方法返回 MagicMock 而不是协程
        # 但 _handle_error 会 await owner.on_error(...)
        # 所以我们需要让 owner.on_error 返回一个协程
        owner = MagicMock()
        owner.on_error = AsyncMock()

        # Should not raise
        await dispatcher._handle_error(owner, exc, event, ctx)


class TestHandlerDispatcherRunHandler:
    """Tests for HandlerDispatcher._run_handler method."""

    @pytest.mark.asyncio
    async def test_run_handler_sync_function(self):
        """_run_handler should handle sync function."""
        peer = MockPeer()

        called = []

        def sync_handler(event: MessageEvent, ctx: Context):
            called.append(True)

        descriptor = HandlerDescriptor(
            id="sync.handler",
            trigger=CommandTrigger(command="sync"),
        )
        handler = LoadedHandler(
            descriptor=descriptor,
            callable=sync_handler,
            owner=MagicMock(),
            legacy_context=None,
        )

        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[handler],
        )

        event = create_message_event()
        ctx = Context(peer=peer, plugin_id="test", cancel_token=CancelToken())

        await dispatcher._run_handler(handler, event, ctx)

        assert called

    @pytest.mark.asyncio
    async def test_run_handler_async_function(self):
        """_run_handler should handle async function."""
        peer = MockPeer()

        called = []

        async def async_handler(event: MessageEvent, ctx: Context):
            called.append(True)

        descriptor = HandlerDescriptor(
            id="async.handler",
            trigger=CommandTrigger(command="async"),
        )
        handler = LoadedHandler(
            descriptor=descriptor,
            callable=async_handler,
            owner=MagicMock(),
            legacy_context=None,
        )

        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[handler],
        )

        event = create_message_event()
        ctx = Context(peer=peer, plugin_id="test", cancel_token=CancelToken())

        await dispatcher._run_handler(handler, event, ctx)

        assert called

    @pytest.mark.asyncio
    async def test_run_handler_async_generator(self):
        """_run_handler should handle async generator."""
        peer = MockPeer()

        replies = []

        async def gen_handler(event: MessageEvent, ctx: Context):
            yield "first"
            yield "second"

        descriptor = HandlerDescriptor(
            id="gen.handler",
            trigger=CommandTrigger(command="gen"),
        )
        handler = LoadedHandler(
            descriptor=descriptor,
            callable=gen_handler,
            owner=MagicMock(),
            legacy_context=None,
        )

        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[handler],
        )

        event = create_message_event()

        # reply_handler 必须是异步的
        async def async_reply(text: str) -> None:
            replies.append(text)

        event._reply_handler = async_reply
        ctx = Context(peer=peer, plugin_id="test", cancel_token=CancelToken())

        await dispatcher._run_handler(handler, event, ctx)

        assert "first" in replies
        assert "second" in replies

    @pytest.mark.asyncio
    async def test_run_handler_with_exception(self):
        """_run_handler should handle exceptions."""
        peer = MockPeer()

        async def failing_handler(event: MessageEvent, ctx: Context):
            raise ValueError("handler error")

        descriptor = HandlerDescriptor(
            id="failing.handler",
            trigger=CommandTrigger(command="fail"),
        )
        # owner.on_error 需要是异步的
        owner = MagicMock()
        owner.on_error = AsyncMock()
        handler = LoadedHandler(
            descriptor=descriptor,
            callable=failing_handler,
            owner=owner,
            legacy_context=None,
        )

        dispatcher = HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[handler],
        )

        event = create_message_event()
        ctx = Context(peer=peer, plugin_id="test", cancel_token=CancelToken())

        with pytest.raises(ValueError, match="handler error"):
            await dispatcher._run_handler(handler, event, ctx)
