from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot_sdk._internal.invocation_context import caller_plugin_scope
from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.protocol.messages import InvokeMessage
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.session_waiter import SessionController
from astrbot_sdk.testing import LocalRuntimeConfig, PluginHarness
from astrbot_sdk._internal.testing_support import MockCapabilityRouter, MockPeer


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
async def test_plugin_harness_dispatches_followup_to_session_waiter(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "session_waiter_plugin"
    _write_session_waiter_plugin(plugin_dir)

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        first_records = await harness.dispatch_text("start", session_id="session-1")
        await asyncio.sleep(0)
        second_records = await harness.dispatch_text("next", session_id="session-1")

    assert [record.text for record in first_records] == ["ready"]
    assert [record.text for record in second_records] == ["followup:next"]


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


@pytest.mark.asyncio
async def test_session_waiter_dispatch_preserves_source_event_payload() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    event_payload = {
        "type": "message",
        "event_type": "message",
        "text": "followup",
        "session_id": "session-1",
        "user_id": "tester",
        "platform": "test",
        "platform_id": "test",
        "message_type": "private",
        "target": {"conversation_id": "session-1", "platform": "test"},
        "raw": {"event_type": "message"},
    }
    event = MessageEvent.from_payload(
        event_payload,
        context=Context(peer=peer, plugin_id="test-plugin"),
    )
    seen_payloads: list[dict[str, object]] = []

    async def capture_waiter(
        controller: SessionController,
        waiter_event: MessageEvent,
    ) -> None:
        source_payload = waiter_event._context._source_event_payload
        seen_payloads.append(dict(source_payload))
        controller.stop()

    async def waiter_task() -> None:
        with caller_plugin_scope("test-plugin"):
            await dispatcher._session_waiters.register(
                event=event,
                handler=capture_waiter,
                timeout=30,
                record_history_chains=False,
            )

    task = asyncio.create_task(waiter_task())
    await asyncio.sleep(0)

    await dispatcher.invoke(
        InvokeMessage(
            id="req-session-waiter",
            capability="handler.invoke",
            input={
                "handler_id": "__sdk_session_waiter__",
                "event": dict(event_payload),
                "args": {},
            },
        ),
        CancelToken(),
    )
    await task

    assert seen_payloads == [event_payload]


@pytest.mark.asyncio
async def test_has_active_waiter_ignores_completed_waiter_before_unregister() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    event = _build_event(text="hello", session_id="session-1", peer=peer)
    release_unregister = asyncio.Event()
    manager = dispatcher._session_waiters
    original_unregister = manager.unregister

    async def delayed_unregister(
        session_key: str,
        *,
        plugin_id: str | None = None,
    ) -> None:
        await release_unregister.wait()
        await original_unregister(session_key, plugin_id=plugin_id)

    manager.unregister = delayed_unregister  # type: ignore[method-assign]

    async def waiter_task() -> None:
        with caller_plugin_scope("test-plugin"):
            await manager.register(
                event=event,
                handler=_noop_waiter,
                timeout=30,
                record_history_chains=False,
            )

    task = asyncio.create_task(waiter_task())
    await asyncio.sleep(0)

    assert dispatcher.has_active_waiter(event) is True

    await manager.fail(event.unified_msg_origin, RuntimeError("stop waiter"))
    await asyncio.sleep(0)

    assert dispatcher.has_active_waiter(event) is False

    release_unregister.set()
    with pytest.raises(RuntimeError, match="stop waiter"):
        await task


@pytest.mark.asyncio
async def test_session_waiter_dispatch_uses_registering_plugin_id() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(
        plugin_id="worker-group",
        peer=peer,
        handlers=[],
    )
    event_payload = {
        "type": "message",
        "event_type": "message",
        "text": "followup",
        "session_id": "session-1",
        "user_id": "tester",
        "platform": "test",
        "platform_id": "test",
        "message_type": "private",
        "raw": {"event_type": "message"},
    }
    register_event = MessageEvent.from_payload(
        event_payload,
        context=Context(peer=peer, plugin_id="plugin.alpha"),
    )
    seen_plugin_ids: list[str] = []

    async def capture_waiter(
        controller: SessionController,
        waiter_event: MessageEvent,
    ) -> None:
        seen_plugin_ids.append(waiter_event._context.plugin_id)
        controller.stop()

    async def waiter_task() -> None:
        with caller_plugin_scope("plugin.alpha"):
            await dispatcher._session_waiters.register(
                event=register_event,
                handler=capture_waiter,
                timeout=30,
                record_history_chains=False,
            )

    task = asyncio.create_task(waiter_task())
    await asyncio.sleep(0)

    await dispatcher.invoke(
        InvokeMessage(
            id="req-session-waiter-plugin-id",
            capability="handler.invoke",
            input={
                "handler_id": "__sdk_session_waiter__",
                "event": dict(event_payload),
                "args": {},
            },
        ),
        CancelToken(),
    )
    await task

    assert seen_plugin_ids == ["plugin.alpha"]


@pytest.mark.asyncio
async def test_session_waiter_dispatch_resolves_session_from_target_payload() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(
        plugin_id="worker-group",
        peer=peer,
        handlers=[],
    )
    register_payload = {
        "type": "message",
        "event_type": "message",
        "text": "followup",
        "session_id": "session-1",
        "user_id": "tester",
        "platform": "test",
        "platform_id": "test",
        "message_type": "private",
        "raw": {"event_type": "message"},
    }
    target_only_payload = {
        "type": "message",
        "event_type": "message",
        "text": "followup",
        "user_id": "tester",
        "platform_id": "test",
        "message_type": "private",
        "target": {"conversation_id": "session-1", "platform": "test"},
        "raw": {"event_type": "message"},
    }
    register_event = MessageEvent.from_payload(
        register_payload,
        context=Context(peer=peer, plugin_id="plugin.alpha"),
    )
    seen_plugin_ids: list[str] = []

    async def capture_waiter(
        controller: SessionController,
        waiter_event: MessageEvent,
    ) -> None:
        seen_plugin_ids.append(waiter_event._context.plugin_id)
        controller.stop()

    async def waiter_task() -> None:
        with caller_plugin_scope("plugin.alpha"):
            await dispatcher._session_waiters.register(
                event=register_event,
                handler=capture_waiter,
                timeout=30,
                record_history_chains=False,
            )

    task = asyncio.create_task(waiter_task())
    await asyncio.sleep(0)

    await dispatcher.invoke(
        InvokeMessage(
            id="req-session-waiter-target-only",
            capability="handler.invoke",
            input={
                "handler_id": "__sdk_session_waiter__",
                "event": dict(target_only_payload),
                "args": {},
            },
        ),
        CancelToken(),
    )
    await task

    assert seen_plugin_ids == ["plugin.alpha"]


@pytest.mark.asyncio
async def test_session_waiters_do_not_replace_across_plugins_same_session() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(
        plugin_id="worker-group",
        peer=peer,
        handlers=[],
    )
    event_payload = {
        "type": "message",
        "event_type": "message",
        "text": "followup",
        "session_id": "session-1",
        "user_id": "tester",
        "platform": "test",
        "platform_id": "test",
        "message_type": "private",
        "raw": {"event_type": "message"},
    }
    event_a = MessageEvent.from_payload(
        event_payload,
        context=Context(peer=peer, plugin_id="plugin.alpha"),
    )
    event_b = MessageEvent.from_payload(
        event_payload,
        context=Context(peer=peer, plugin_id="plugin.beta"),
    )
    seen_plugin_ids: list[str] = []

    async def waiter_alpha(
        controller: SessionController,
        waiter_event: MessageEvent,
    ) -> None:
        seen_plugin_ids.append(waiter_event._context.plugin_id)
        controller.stop()

    async def waiter_beta(
        controller: SessionController,
        waiter_event: MessageEvent,
    ) -> None:
        seen_plugin_ids.append(waiter_event._context.plugin_id)
        controller.stop()

    async def task_alpha() -> None:
        with caller_plugin_scope("plugin.alpha"):
            await dispatcher._session_waiters.register(
                event=event_a,
                handler=waiter_alpha,
                timeout=30,
                record_history_chains=False,
            )

    async def task_beta() -> None:
        with caller_plugin_scope("plugin.beta"):
            await dispatcher._session_waiters.register(
                event=event_b,
                handler=waiter_beta,
                timeout=30,
                record_history_chains=False,
            )

    waiter_task_alpha = asyncio.create_task(task_alpha())
    waiter_task_beta = asyncio.create_task(task_beta())
    await asyncio.sleep(0)

    assert sorted(dispatcher._session_waiters.get_waiter_plugin_ids("session-1")) == [
        "plugin.alpha",
        "plugin.beta",
    ]

    await dispatcher._session_waiters.dispatch(
        MessageEvent.from_payload(
            event_payload,
            context=Context(peer=peer, plugin_id="plugin.alpha"),
        ),
        plugin_id="plugin.alpha",
    )
    await dispatcher._session_waiters.dispatch(
        MessageEvent.from_payload(
            event_payload,
            context=Context(peer=peer, plugin_id="plugin.beta"),
        ),
        plugin_id="plugin.beta",
    )
    await waiter_task_alpha
    await waiter_task_beta

    assert sorted(seen_plugin_ids) == ["plugin.alpha", "plugin.beta"]


@pytest.mark.asyncio
async def test_session_waiter_dispatch_accepts_explicit_plugin_id_for_ambiguous_session() -> (
    None
):
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(
        plugin_id="worker-group",
        peer=peer,
        handlers=[],
    )
    event_payload = {
        "type": "message",
        "event_type": "message",
        "text": "followup",
        "session_id": "session-1",
        "user_id": "tester",
        "platform": "test",
        "platform_id": "test",
        "message_type": "private",
        "raw": {"event_type": "message"},
    }
    event_a = MessageEvent.from_payload(
        event_payload,
        context=Context(peer=peer, plugin_id="plugin.alpha"),
    )
    event_b = MessageEvent.from_payload(
        event_payload,
        context=Context(peer=peer, plugin_id="plugin.beta"),
    )
    seen_plugin_ids: list[str] = []

    async def waiter_alpha(
        controller: SessionController,
        waiter_event: MessageEvent,
    ) -> None:
        seen_plugin_ids.append(waiter_event._context.plugin_id)
        controller.stop()

    async def waiter_beta(
        controller: SessionController,
        waiter_event: MessageEvent,
    ) -> None:
        seen_plugin_ids.append(waiter_event._context.plugin_id)
        controller.stop()

    async def task_alpha() -> None:
        with caller_plugin_scope("plugin.alpha"):
            await dispatcher._session_waiters.register(
                event=event_a,
                handler=waiter_alpha,
                timeout=30,
                record_history_chains=False,
            )

    async def task_beta() -> None:
        with caller_plugin_scope("plugin.beta"):
            await dispatcher._session_waiters.register(
                event=event_b,
                handler=waiter_beta,
                timeout=30,
                record_history_chains=False,
            )

    waiter_task_alpha = asyncio.create_task(task_alpha())
    waiter_task_beta = asyncio.create_task(task_beta())
    await asyncio.sleep(0)

    with pytest.raises(LookupError, match="explicit plugin identity"):
        await dispatcher.invoke(
            InvokeMessage(
                id="req-session-waiter-ambiguous",
                capability="handler.invoke",
                input={
                    "handler_id": "__sdk_session_waiter__",
                    "event": dict(event_payload),
                    "args": {},
                },
            ),
            CancelToken(),
        )

    await dispatcher.invoke(
        InvokeMessage(
            id="req-session-waiter-explicit-alpha",
            capability="handler.invoke",
            input={
                "handler_id": "__sdk_session_waiter__",
                "plugin_id": "plugin.alpha",
                "event": dict(event_payload),
                "args": {},
            },
        ),
        CancelToken(),
    )
    await dispatcher.invoke(
        InvokeMessage(
            id="req-session-waiter-explicit-beta",
            capability="handler.invoke",
            input={
                "handler_id": "__sdk_session_waiter__",
                "plugin_id": "plugin.beta",
                "event": dict(event_payload),
                "args": {},
            },
        ),
        CancelToken(),
    )

    await waiter_task_alpha
    await waiter_task_beta

    assert sorted(seen_plugin_ids) == ["plugin.alpha", "plugin.beta"]


@pytest.mark.asyncio
async def test_fail_without_plugin_id_does_not_broadcast_across_plugins() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(
        plugin_id="worker-group",
        peer=peer,
        handlers=[],
    )
    event_payload = {
        "type": "message",
        "event_type": "message",
        "text": "followup",
        "session_id": "session-1",
        "user_id": "tester",
        "platform": "test",
        "platform_id": "test",
        "message_type": "private",
        "raw": {"event_type": "message"},
    }
    event_a = MessageEvent.from_payload(
        event_payload,
        context=Context(peer=peer, plugin_id="plugin.alpha"),
    )
    event_b = MessageEvent.from_payload(
        event_payload,
        context=Context(peer=peer, plugin_id="plugin.beta"),
    )

    async def waiter_alpha() -> None:
        with caller_plugin_scope("plugin.alpha"):
            await dispatcher._session_waiters.register(
                event=event_a,
                handler=_noop_waiter,
                timeout=30,
                record_history_chains=False,
            )

    async def waiter_beta() -> None:
        with caller_plugin_scope("plugin.beta"):
            await dispatcher._session_waiters.register(
                event=event_b,
                handler=_noop_waiter,
                timeout=30,
                record_history_chains=False,
            )

    task_a = asyncio.create_task(waiter_alpha())
    task_b = asyncio.create_task(waiter_beta())
    await asyncio.sleep(0)

    assert (
        await dispatcher._session_waiters.fail(
            "session-1",
            RuntimeError("stop waiter"),
        )
        is False
    )
    assert dispatcher.has_active_waiter(event_a) is True
    assert dispatcher.has_active_waiter(event_b) is True

    await dispatcher._session_waiters.fail(
        "session-1",
        RuntimeError("stop alpha"),
        plugin_id="plugin.alpha",
    )
    with pytest.raises(RuntimeError, match="stop alpha"):
        await task_a

    assert dispatcher.has_active_waiter(event_b) is True
    await dispatcher._session_waiters.fail(
        "session-1",
        RuntimeError("stop beta"),
        plugin_id="plugin.beta",
    )
    with pytest.raises(RuntimeError, match="stop beta"):
        await task_b


@pytest.mark.asyncio
async def test_plugin_harness_waits_for_waiter_side_effects_after_stop(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "session_waiter_stop_after_side_effects"
    _write_session_waiter_plugin(plugin_dir)
    (plugin_dir / "main.py").write_text(
        "\n".join(
            [
                "import asyncio",
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
                "        controller.stop()",
                "        await asyncio.sleep(0)",
                '        await event.reply(f"followup:{event.text}")',
                "",
            ]
        ),
        encoding="utf-8",
    )

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        first_records = await harness.dispatch_text("start", session_id="session-1")
        second_records = await harness.dispatch_text("next", session_id="session-1")

    assert [record.text for record in first_records] == ["ready"]
    assert [record.text for record in second_records] == ["followup:next"]


async def _noop_waiter(
    controller: SessionController,
    waiter_event: MessageEvent,
) -> None:
    del waiter_event
    controller.stop()
