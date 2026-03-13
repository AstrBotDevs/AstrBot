"""Tests for the public local-dev/testing helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import astrbot_sdk.testing as testing_module
from astrbot_sdk.testing import (
    LocalRuntimeConfig,
    MockCapabilityRouter,
    MockContext,
    MockMessageEvent,
    MockPeer,
    PluginHarness,
)


class TestTestingModule:
    """Tests for `astrbot_sdk.testing` exports and behavior."""

    def test_public_all_matches_stable_testing_surface(self):
        """testing.__all__ should stay aligned with the documented stable helper API."""
        assert testing_module.__all__ == [
            "InMemoryDB",
            "InMemoryMemory",
            "LocalRuntimeConfig",
            "MockCapabilityRouter",
            "MockContext",
            "MockLLMClient",
            "MockMessageEvent",
            "MockPeer",
            "MockPlatformClient",
            "PluginHarness",
            "RecordedSend",
            "StdoutPlatformSink",
        ]

    @pytest.mark.asyncio
    async def test_mock_peer_stream_emits_event_messages(self):
        """MockPeer.invoke_stream should behave like a peer-level event stream."""
        router = MockCapabilityRouter()
        peer = MockPeer(router)

        stream = await peer.invoke_stream(
            "llm.stream_chat",
            {"prompt": "hi"},
            include_completed=True,
        )
        phases = []
        chunks = []
        async for event in stream:
            phases.append(event.phase)
            if event.phase == "delta":
                chunks.append(event.data["text"])

        assert phases[0] == "started"
        assert phases[-1] == "completed"
        assert "".join(chunks) == "Echo: hi"

    @pytest.mark.asyncio
    async def test_plugin_harness_dispatches_v4_sample_plugin(self):
        """PluginHarness should run the maintained v4 sample against the local mock core."""
        harness = PluginHarness(
            LocalRuntimeConfig(plugin_dir=Path("test_plugin/new")),
        )

        async with harness:
            records = await harness.dispatch_text("hello")

        assert [item.text for item in records if item.kind == "text"] == [
            "Echo: hello",
            "Echo: stream",
        ]

    @pytest.mark.asyncio
    async def test_plugin_harness_can_invoke_plugin_capabilities(self):
        """Harness should expose plugin-provided capabilities for local assertions."""
        harness = PluginHarness(
            LocalRuntimeConfig(plugin_dir=Path("test_plugin/new")),
        )

        async with harness:
            result = await harness.invoke_capability("demo.echo", {"text": "abc"})

        assert result == {
            "echo": "abc",
            "plugin_id": "astrbot_plugin_v4demo",
        }

    @pytest.mark.asyncio
    async def test_mock_context_and_event_support_direct_handler_unit_tests(self):
        """MockContext/MockMessageEvent should support direct handler tests without a full harness."""
        ctx = MockContext(plugin_id="demo-test")
        event = MockMessageEvent(text="hello", context=ctx)
        ctx.llm.mock_response("你好！")

        async def handler(mock_event, mock_ctx):
            reply = await mock_ctx.llm.chat("hello")
            await mock_event.reply(reply)
            return mock_event.plain_result("done")

        result = await handler(event, ctx)

        assert result.text == "done"
        assert event.replies == ["你好！"]
        ctx.platform.assert_sent("你好！")

    @pytest.mark.asyncio
    async def test_plugin_harness_reuses_session_waiter_across_followups(
        self,
        tmp_path: Path,
    ):
        """Follow-up messages from the same session should be routed into the active waiter."""
        plugin_dir = tmp_path / "legacy_waiter"
        plugin_dir.mkdir()
        (plugin_dir / "main.py").write_text(
            """
from astrbot.core.utils.session_waiter import SessionController, session_waiter
from astrbot_sdk.api.components.command import CommandComponent
from astrbot_sdk.api.event import AstrMessageEvent, filter
from astrbot_sdk.api.message import MessageChain


class WaiterPlugin(CommandComponent):
    @filter.command("ask")
    async def ask(self, event: AstrMessageEvent):
        await event.send(MessageChain().message("请输入确认内容"))

        @session_waiter(timeout=0.2)
        async def waiter(controller: SessionController, ev: AstrMessageEvent):
            await ev.send(MessageChain().message(f"收到:{ev.message_str}"))
            controller.stop()

        await waiter(event)
""".strip(),
            encoding="utf-8",
        )

        harness = PluginHarness(
            LocalRuntimeConfig(plugin_dir=plugin_dir, platform="test"),
        )

        async with harness:
            first = asyncio.create_task(harness.dispatch_text("ask"))
            await asyncio.sleep(0.05)
            follow_up = await harness.dispatch_text("确认")
            await first

        assert [item.text for item in follow_up if item.kind == "text"] == ["收到:确认"]
        assert [item.text for item in harness.sent_messages if item.kind == "text"] == [
            "请输入确认内容",
            "收到:确认",
        ]
