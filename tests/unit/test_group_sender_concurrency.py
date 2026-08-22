import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.follow_up import FollowUpCoordinator
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.group_sender_concurrency import (
    GroupOutboundGate,
    is_group_sender_concurrent,
    session_lock_key,
)
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.platform.message_type import MessageType
from astrbot.core.utils.session_lock import SessionLockManager
from tests.unit.agent_sub_stage_support import (
    FakeInternalProcessEvent,
    _AsyncLockContext,
    _fake_build_cfg,
    _internal_plugin_context,
    _pipeline_context,
)


def _group_event(*, sender_id: str = "user-a", extras: dict | None = None):
    event = FakeInternalProcessEvent(extras=extras)
    event.unified_msg_origin = "aiocqhttp:GroupMessage:group-1"
    event.get_sender_id = lambda: sender_id
    event.get_message_type = lambda: MessageType.GROUP_MESSAGE
    return event


def _concurrent_config(**overrides):
    settings = {
        "group_sender_concurrency": True,
        "unique_session": False,
    }
    settings.update(overrides)
    return {"platform_settings": settings}


def test_group_sender_concurrency_defaults_off():
    assert DEFAULT_CONFIG["platform_settings"]["group_sender_concurrency"] is False
    event = _group_event()
    assert is_group_sender_concurrent(event, DEFAULT_CONFIG) is False
    assert session_lock_key(event.unified_msg_origin, "user-a", concurrent=False) == (
        event.unified_msg_origin
    )


def test_unique_session_ignores_sender_concurrency():
    event = _group_event()
    assert (
        is_group_sender_concurrent(
            event,
            _concurrent_config(unique_session=True),
        )
        is False
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"extras": {"action_type": "live"}},
        {"extras": {"active_reply": True}},
        {"extras": {"cron_job": {"id": "1"}}},
        {"sender_id": ""},
        {"sender_id": "   "},
    ],
)
def test_live_proactive_and_missing_sender_stay_on_umo_lock(kwargs):
    extras = kwargs.get("extras")
    sender_id = kwargs.get("sender_id", "user-a")
    event = _group_event(sender_id=sender_id, extras=extras)
    if "cron_job" in (extras or {}):
        event.platform_meta = SimpleNamespace(
            name="cron", support_streaming_message=True
        )
    assert is_group_sender_concurrent(event, _concurrent_config()) is False


def test_private_chat_is_not_concurrent():
    event = FakeInternalProcessEvent()
    event.get_sender_id = lambda: "user-a"
    event.get_message_type = lambda: MessageType.FRIEND_MESSAGE
    assert is_group_sender_concurrent(event, _concurrent_config()) is False


def test_sender_lock_key_includes_umo_and_sender():
    umo = "aiocqhttp:GroupMessage:group-1"
    key = session_lock_key(umo, "user-a", concurrent=True)
    assert key.startswith(umo)
    assert "user-a" in key
    assert key != session_lock_key(umo, "user-b", concurrent=True)


@pytest.mark.asyncio
async def test_internal_process_uses_sender_lock_when_enabled(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = True
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = SimpleNamespace()
    ctx = _internal_plugin_context()
    ctx.get_config = lambda **_kwargs: _concurrent_config()
    ctx.group_outbound_gate = GroupOutboundGate()
    stage.ctx = _pipeline_context(ctx)
    event = _group_event()
    keys: list[str] = []
    streaming: list[bool] = []

    def capture_lock(key: str):
        keys.append(key)
        return _AsyncLockContext()

    def capture_replace(_cfg, **kwargs):
        streaming.append(kwargs.get("streaming_response"))
        return _fake_build_cfg(**kwargs)

    monkeypatch.setattr(ctx.session_lock_manager, "acquire_lock", capture_lock)
    monkeypatch.setattr(internal, "replace", capture_replace)
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(internal, "build_main_agent", AsyncMock(return_value=None))

    [item async for item in stage.process(event, provider_wake_prefix="")]

    assert keys == [
        session_lock_key(event.unified_msg_origin, "user-a", concurrent=True)
    ]
    assert event.get_extra("_group_outbound_turn") is True
    assert streaming == [False]


@pytest.mark.asyncio
async def test_internal_process_keeps_umo_lock_when_disabled(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = SimpleNamespace()
    ctx = _internal_plugin_context()
    ctx.get_config = lambda **_kwargs: DEFAULT_CONFIG
    stage.ctx = _pipeline_context(ctx)
    event = _group_event()
    keys: list[str] = []

    monkeypatch.setattr(
        ctx.session_lock_manager,
        "acquire_lock",
        lambda key: keys.append(key) or _AsyncLockContext(),
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(internal, "build_main_agent", AsyncMock(return_value=None))

    [item async for item in stage.process(event, provider_wake_prefix="")]

    assert keys == [event.unified_msg_origin]


@pytest.mark.asyncio
async def test_two_senders_do_not_share_llm_lock():
    manager = SessionLockManager()
    umo = "aiocqhttp:GroupMessage:group-1"
    order: list[str] = []

    async def run(sender: str):
        async with manager.acquire_lock(session_lock_key(umo, sender, concurrent=True)):
            order.append(f"{sender}-start")
            await asyncio.sleep(0.05)
            order.append(f"{sender}-end")

    await asyncio.gather(run("a"), run("b"))
    assert order[0].endswith("start")
    assert order[1].endswith("start")


@pytest.mark.asyncio
async def test_same_sender_llm_lock_is_exclusive():
    manager = SessionLockManager()
    umo = "aiocqhttp:GroupMessage:group-1"
    order: list[str] = []

    async def run(label: str):
        async with manager.acquire_lock(session_lock_key(umo, "same", concurrent=True)):
            order.append(f"{label}-start")
            await asyncio.sleep(0.02)
            order.append(f"{label}-end")

    await asyncio.gather(run("first"), run("second"))
    assert order[1].endswith("end")
    assert order[0].endswith("start")


@pytest.mark.asyncio
async def test_outbound_turn_blocks_other_sender_until_release():
    gate = GroupOutboundGate()
    event_a = object()
    umo = "aiocqhttp:GroupMessage:group-1"
    order: list[str] = []

    async def sender_a():
        await gate.hold_turn(umo, event_a)
        order.append("a-hold")
        await asyncio.sleep(0.05)
        order.append("a-release")
        await gate.release_turn(event_a)

    async def sender_b():
        await asyncio.sleep(0.01)
        async with gate.around_send(umo):
            order.append("b-send")

    await asyncio.gather(sender_a(), sender_b())
    assert order == ["a-hold", "a-release", "b-send"]


@pytest.mark.asyncio
async def test_outbound_lock_releases_on_cancel():
    gate = GroupOutboundGate()
    event_a = object()
    umo = "g1"
    released = asyncio.Event()

    async def holder():
        await gate.hold_turn(umo, event_a)
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            await gate.release_turn(event_a)
            released.set()
            raise

    task = asyncio.create_task(holder())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert released.is_set()
    async with gate.around_send(umo):
        pass


@pytest.mark.asyncio
async def test_follow_up_registers_per_sender_and_does_not_clobber_umo_slot():
    coordinator = FollowUpCoordinator()
    native_runner = SimpleNamespace(
        run_context=SimpleNamespace(
            context=SimpleNamespace(
                event=SimpleNamespace(
                    get_sender_id=lambda: "native",
                    get_extra=lambda _k: None,
                    message_obj=None,
                )
            )
        ),
        follow_up=lambda message_text: SimpleNamespace(
            seq=1,
            consumed=False,
            resolved=asyncio.Event(),
            text=message_text,
        ),
    )
    sender_runner = SimpleNamespace(
        run_context=SimpleNamespace(
            context=SimpleNamespace(
                event=SimpleNamespace(
                    get_sender_id=lambda: "user-a",
                    get_extra=lambda _k: None,
                    message_obj=None,
                )
            )
        ),
        follow_up=lambda message_text: SimpleNamespace(
            seq=2,
            consumed=False,
            resolved=asyncio.Event(),
            text=message_text,
        ),
    )
    coordinator.register_active_runner("umo-1", native_runner)
    coordinator.register_active_runner("umo-1", sender_runner, sender_id="user-a")

    assert coordinator._active_runners["umo-1"] is native_runner
    assert coordinator._active_runners[("umo-1", "user-a")] is sender_runner

    class CaptureEvent:
        unified_msg_origin = "umo-1"

        def get_sender_id(self):
            return "user-a"

        def get_message_str(self):
            return "follow"

        def get_message_outline(self):
            return ""

    capture = coordinator.try_capture(CaptureEvent())
    assert capture is not None
    assert capture.order_key == ("umo-1", "user-a")
    capture.ticket.resolved.set()
    await coordinator.finalize_capture(
        capture,
        activated=False,
        consumed_marked=False,
    )
    coordinator.unregister_active_runner("umo-1", sender_runner, sender_id="user-a")
    assert coordinator._active_runners["umo-1"] is native_runner
