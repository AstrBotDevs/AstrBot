from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot_sdk._invocation_context import caller_plugin_scope
from astrbot_sdk.context import Context
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.session_waiter import SessionController
from astrbot_sdk.testing import LocalRuntimeConfig, PluginHarness
from astrbot_sdk._testing_support import MockCapabilityRouter, MockPeer


def _write_session_waiter_plugin(plugin_dir: Path) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "name: session_waiter_plugin",
                "display_name: Session Waiter Plugin",
                "desc: test plugin",
                "author: tests",
                "version: 0.1.0",
                "runtime:",
                '  python: "3.11"',
                "components:",
                "  - class: main:SessionWaiterPlugin",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "\n".join(
            [
                "from astrbot_sdk import Context, MessageEvent, SessionController, Star, on_command, session_waiter",
                "",
                "",
                "class SessionWaiterPlugin(Star):",
                '    @on_command("start")',
                "    async def start(self, event: MessageEvent, ctx: Context) -> None:",
                '        await event.reply("ready")',
                '        await ctx.register_task(self.wait_for_followup(event), "wait for followup")',
                "",
                "    @session_waiter(timeout=30)",
                "    async def wait_for_followup(",
                "        self,",
                "        controller: SessionController,",
                "        event: MessageEvent,",
                "    ) -> None:",
                "        del controller",
                '        await event.reply(f"followup:{event.text}")',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")


def _build_event(*, text: str, session_id: str, peer: MockPeer) -> MessageEvent:
    return MessageEvent.from_payload(
        {
            "type": "message",
            "event_type": "message",
            "text": text,
            "session_id": session_id,
            "user_id": "tester",
            "platform": "test",
            "platform_id": "test",
            "message_type": "private",
            "raw": {"event_type": "message"},
        },
        context=Context(peer=peer, plugin_id="test-plugin"),
    )


def test_plugin_harness_waiter_probe_uses_dispatcher_public_api(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "session_waiter_plugin"
    _write_session_waiter_plugin(plugin_dir)
    harness = PluginHarness(LocalRuntimeConfig(plugin_dir=plugin_dir))
    peer = MockPeer(MockCapabilityRouter())
    probe_event = _build_event(text="hello", session_id="session-1", peer=peer)
    harness.lifecycle_context = probe_event._context

    calls: list[MessageEvent] = []

    def has_active_waiter(event: MessageEvent) -> bool:
        calls.append(event)
        return True

    harness.dispatcher = SimpleNamespace(has_active_waiter=has_active_waiter)

    assert harness._has_waiter_for_event(probe_event.to_payload()) is True
    assert len(calls) == 1
    assert calls[0].unified_msg_origin == "session-1"


@pytest.mark.asyncio
async def test_handler_dispatcher_exposes_active_waiter_probe() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    event = _build_event(text="hello", session_id="session-1", peer=peer)

    assert dispatcher.has_active_waiter(event) is False

    async def waiter_task() -> None:
        with caller_plugin_scope("test-plugin"):
            await dispatcher._session_waiters.register(
                event=event,
                handler=_noop_waiter,
                timeout=30,
                record_history_chains=False,
            )

    task = asyncio.create_task(waiter_task())
    await asyncio.sleep(0)

    assert dispatcher.has_active_waiter(event) is True

    await dispatcher._session_waiters.fail(
        event.unified_msg_origin, RuntimeError("stop waiter")
    )
    with pytest.raises(RuntimeError, match="stop waiter"):
        await task
    assert dispatcher.has_active_waiter(event) is False


async def _noop_waiter(
    controller: SessionController,
    waiter_event: MessageEvent,
) -> None:
    del waiter_event
    controller.stop()
