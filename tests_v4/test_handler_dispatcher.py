from __future__ import annotations

import pytest

from astrbot_sdk._invocation_context import current_caller_plugin_id
from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.protocol.descriptors import (
    CapabilityDescriptor,
    HandlerDescriptor,
    MessageTrigger,
)
from astrbot_sdk.runtime.handler_dispatcher import (
    CapabilityDispatcher,
    HandlerDispatcher,
)
from astrbot_sdk.runtime.loader import LoadedCapability, LoadedHandler
from astrbot_sdk.testing import MockCapabilityRouter, MockPeer


def _peer():
    return MockPeer(MockCapabilityRouter())


class TestHandlerDispatcherArgumentValidation:
    def test_handler_dispatcher_raises_for_uninjectable_required_param(self):
        peer = _peer()
        dispatcher = HandlerDispatcher(plugin_id="demo", peer=peer, handlers=[])
        ctx = Context(peer=peer, plugin_id="demo", cancel_token=CancelToken())
        event = MessageEvent(text="hello", session_id="s1", context=ctx)

        async def bad_handler(event: MessageEvent, missing: str) -> None:
            return None

        with pytest.raises(TypeError, match="必填参数 'missing' 无法注入"):
            dispatcher._build_args(bad_handler, event, ctx, args={})

    def test_capability_dispatcher_raises_for_uninjectable_required_param(self):
        peer = _peer()
        capability = LoadedCapability(
            descriptor=CapabilityDescriptor(name="demo.cap", description="demo"),
            callable=lambda ctx, missing: {"ok": True},
            owner=object(),
            plugin_id="demo",
        )
        dispatcher = CapabilityDispatcher(
            plugin_id="demo",
            peer=peer,
            capabilities=[capability],
        )
        ctx = Context(peer=peer, plugin_id="demo", cancel_token=CancelToken())

        with pytest.raises(TypeError, match="必填参数 'missing' 无法注入"):
            dispatcher._build_args(
                capability.callable,
                payload={},
                ctx=ctx,
                cancel_token=CancelToken(),
            )


class TestHandlerDispatcherInvoke:
    @pytest.mark.asyncio
    async def test_invoke_reports_missing_injected_param(self):
        peer = _peer()

        async def bad_handler(event: MessageEvent, missing: str) -> None:
            return None

        loaded = LoadedHandler(
            descriptor=HandlerDescriptor(
                id="demo:plugin.bad_handler",
                trigger=MessageTrigger(),
            ),
            callable=bad_handler,
            owner=object(),
            plugin_id="demo",
        )
        dispatcher = HandlerDispatcher(plugin_id="demo", peer=peer, handlers=[loaded])

        class Message:
            id = "req-1"
            input = {
                "handler_id": "demo:plugin.bad_handler",
                "event": {"text": "hello", "session_id": "s1"},
            }

        with pytest.raises(TypeError, match="必填参数 'missing' 无法注入"):
            await dispatcher.invoke(Message(), CancelToken())

    @pytest.mark.asyncio
    async def test_invoke_binds_runtime_caller_plugin_id_for_raw_peer_calls(self):
        seen: list[str | None] = []

        class RecordingPeer:
            remote_capability_map = {}
            remote_peer = object()

            async def invoke(self, capability, payload, *, stream=False):
                seen.append(current_caller_plugin_id())
                return {"ok": True}

        peer = RecordingPeer()

        async def handler(ctx: Context) -> None:
            await ctx.peer.invoke("metadata.list_plugins", {}, stream=False)

        loaded = LoadedHandler(
            descriptor=HandlerDescriptor(
                id="demo:plugin.handler",
                trigger=MessageTrigger(),
            ),
            callable=handler,
            owner=object(),
            plugin_id="demo",
        )
        dispatcher = HandlerDispatcher(plugin_id="demo", peer=peer, handlers=[loaded])

        class Message:
            id = "req-2"
            input = {
                "handler_id": "demo:plugin.handler",
                "event": {"text": "hello", "session_id": "s1"},
            }

        await dispatcher.invoke(Message(), CancelToken())

        assert seen == ["demo"]
