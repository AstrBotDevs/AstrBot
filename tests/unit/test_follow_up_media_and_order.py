"""Tests for preserving media/quoted inputs and strict ordering in follow-up capture."""

from __future__ import annotations

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import CallToolResult, TextContent
from PIL import Image as PILImage

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.input import ImageInput, PlainInput
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runtime import (
    AgentInput,
    AgentPermissions,
    AgentRole,
    AgentSessionRef,
    InputReceipt,
)
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent_input import extract_plain_steering_text
from astrbot.core.astr_agent_runtime import AstrAgentRuntime
from astrbot.core.astr_agent_runtime import session as native_session
from astrbot.core.astr_agent_runtime.main_agent import MainAgentBuildResult
from astrbot.core.astr_agent_runtime.main_agent import builder as native_builder
from astrbot.core.astr_agent_runtime.main_agent.request import prepare_request
from astrbot.core.astr_agent_runtime.runner import AgentRunner
from astrbot.core.astr_agent_runtime.session import NativeAgentSession
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.event_bus import EventBus
from astrbot.core.message.components import (
    At,
    Face,
    File,
    Image,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.process_stage import follow_up
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import (
    AstrMessageEvent,
    current_message_event,
)
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.utils.active_event_registry import active_event_registry


def _make_event(
    text: str = "",
    components: list | None = None,
    *,
    session_id: str = "user-1",
    sender_id: str = "alice",
    message_id: str = "msg-1",
    message_type: MessageType = MessageType.FRIEND_MESSAGE,
) -> AstrMessageEvent:
    msg = AstrBotMessage()
    msg.type = message_type
    msg.self_id = "bot"
    msg.session_id = session_id
    msg.message_id = message_id
    msg.sender = MessageMember(user_id=sender_id, nickname=sender_id)
    msg.message = (
        list(components) if components is not None else ([Plain(text)] if text else [])
    )
    msg.message_str = text
    event = AstrMessageEvent(
        text,
        msg,
        PlatformMetadata(id="target", name="aiocqhttp", description="Target"),
        session_id,
    )
    event.is_at_or_wake_command = True
    event.is_wake = True
    return event


def _make_fake_turn(
    event: AstrMessageEvent,
    *,
    turn_id: str = "turn-1",
    pending_turn_count: int = 0,
    steer_impl=None,
):
    receipts: list[tuple[AgentInput, InputReceipt]] = []

    def default_steer(agent_input: AgentInput) -> InputReceipt | None:
        receipt = InputReceipt()
        receipts.append((agent_input, receipt))
        return receipt

    turn = SimpleNamespace(
        id=turn_id,
        input=AgentInput(event=event, permissions=AgentPermissions(AgentRole.MEMBER)),
        session=SimpleNamespace(pending_turn_count=pending_turn_count),
        steer=MagicMock(side_effect=steer_impl or default_steer),
        receipts=receipts,
    )
    return turn


@pytest.fixture(autouse=True)
def _clean_follow_up_state():
    follow_up._FOLLOW_UP_ORDER_STATE.clear()
    yield
    follow_up._FOLLOW_UP_ORDER_STATE.clear()


# ---------------------------------------------------------------------------
# Unit tests: extract_plain_steering_text
# ---------------------------------------------------------------------------


def test_extract_plain_steering_text_allows_plain_and_preserves_whitespace():
    event = _make_event("  keep spaces  ", [Plain("  keep spaces  ")])
    assert extract_plain_steering_text(event) == "  keep spaces  "


def test_extract_plain_steering_text_allows_at_and_face_with_plain_text():
    event = _make_event(
        "change direction",
        [At(qq="bot"), Plain(" change direction"), Face(id=1)],
        message_type=MessageType.GROUP_MESSAGE,
    )
    assert extract_plain_steering_text(event) == "change direction"


def test_extract_plain_steering_text_allows_stt_replaced_plain_text():
    # After PreProcessStage STT succeeds, Record is replaced by Plain and text appended.
    event = _make_event("transcribed voice", [Plain("transcribed voice")])
    assert extract_plain_steering_text(event) == "transcribed voice"


@pytest.mark.parametrize(
    ("text", "components"),
    [
        ("", [Image(file="photo.png")]),
        ("look at this", [Plain("look at this"), Image(file="photo.png")]),
        ("", [Record(file="voice.wav")]),
        ("listen", [Plain("listen"), Record(file="voice.wav")]),
        ("", [Video(file="clip.mp4")]),
        ("watch", [Plain("watch"), Video(file="clip.mp4")]),
        ("", [File(name="report.pdf", file="report.pdf")]),
        ("summarize", [Plain("summarize"), File(name="report.pdf", file="report.pdf")]),
        (
            "",
            [Reply(id="r1", sender_nickname="Bob", chain=[Image(file="quoted.png")])],
        ),
        (
            "what is this?",
            [
                Reply(id="r2", sender_nickname="Bob", chain=[Image(file="quoted.png")]),
                Plain("what is this?"),
            ],
        ),
        (
            "explain this",
            [
                Reply(
                    id="r3",
                    sender_nickname="Bob",
                    message_str="Important quoted text",
                    chain=[Plain("Important quoted text")],
                ),
                Plain("explain this"),
            ],
        ),
        ("comment", [Reply(id="r4", chain=None), Plain("comment")]),
        ("", [Reply(id="r5", chain=None)]),
        ("   ", [Plain("   ")]),
        ("", []),
    ],
)
def test_extract_plain_steering_text_rejects_media_reply_and_empty(text, components):
    event = _make_event(text, components)
    assert extract_plain_steering_text(event) is None


def test_extract_plain_steering_text_rejects_structured_extras_and_tool_result():
    with_req = _make_event("hello")
    with_req.set_extra("provider_request", ProviderRequest(prompt="custom"))
    assert extract_plain_steering_text(with_req) is None

    with_excerpt = _make_event("explain")
    with_excerpt.set_extra("thread_selected_text", "Selected snippet")
    assert extract_plain_steering_text(with_excerpt) is None

    wakeup = AgentWakeupEvent(
        context=SimpleNamespace(),
        session=MessageSession.from_str("target:FriendMessage:user-1"),
        platform_meta=PlatformMetadata(id="target", name="aiocqhttp", description="T"),
        prompt="Background done",
        source="background_task",
        tool_result=(
            "slow_tool",
            CallToolResult(content=[TextContent(type="text", text="done")]),
        ),
    )
    assert extract_plain_steering_text(wakeup) is None


# ---------------------------------------------------------------------------
# Unit tests: NativeAgentSession.steer_turn defense-in-depth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_native_session_steer_turn_rejects_non_plain_event_and_preserves_portable():
    session = NativeAgentSession(SimpleNamespace(), "conv-1", "target:FriendMessage:u1")
    runner = SimpleNamespace(follow_up=MagicMock(return_value=SimpleNamespace()))
    session._runner = runner
    turn = SimpleNamespace(id="turn-1")

    image_event = _make_event("", [Image(file="pic.png")])
    assert (
        session.steer_turn(
            turn,
            AgentInput(event=image_event, permissions=AgentPermissions()),
        )
        is None
    )
    mixed_event = _make_event("see image", [Plain("see image"), Image(file="pic.png")])
    assert (
        session.steer_turn(
            turn,
            AgentInput(event=mixed_event, permissions=AgentPermissions()),
        )
        is None
    )
    reply_event = _make_event(
        "why?",
        [Reply(id="r1", sender_nickname="Bob", message_str="quote"), Plain("why?")],
    )
    assert (
        session.steer_turn(
            turn,
            AgentInput(event=reply_event, permissions=AgentPermissions()),
        )
        is None
    )
    runner.follow_up.assert_not_called()

    plain_event = _make_event("  focus on tests  ")
    receipt = session.steer_turn(
        turn,
        AgentInput(event=plain_event, permissions=AgentPermissions()),
    )
    assert receipt is not None
    runner.follow_up.assert_called_once_with(
        message_text="  focus on tests  ", temp_text=None
    )

    runner.follow_up.reset_mock()
    portable_receipt = session.steer_turn(
        turn,
        AgentInput(
            event=image_event,
            permissions=AgentPermissions(),
            content=[PlainInput(text="Check this"), ImageInput(path="/tmp/a.png")],
        ),
    )
    assert portable_receipt is not None
    runner.follow_up.assert_called_once_with(
        message_text="Check this\n[image] /tmp/a.png", temp_text=None
    )


# ---------------------------------------------------------------------------
# Unit tests: follow_up.py ordering barrier, release, and cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_text_follow_ups_still_steer_fifo_without_blocking_each_other():
    e1 = _make_event("first run", message_id="m1")
    turn1 = _make_fake_turn(e1, turn_id="t1")

    e2 = _make_event("follow up 1", message_id="m2")
    e3 = _make_event("follow up 2", message_id="m3")
    c2 = follow_up.try_capture_follow_up(e2, turn1)
    c3 = follow_up.try_capture_follow_up(e3, turn1)

    assert c2 is not None and c2.receipt is not None
    assert c3 is not None and c3.receipt is not None
    assert turn1.steer.call_count == 2

    t2 = asyncio.create_task(follow_up.prepare_follow_up_capture(c2))
    t3 = asyncio.create_task(follow_up.prepare_follow_up_capture(c3))
    await asyncio.sleep(0)

    c2.receipt.resolve(True)
    c3.receipt.resolve(True)
    assert await t2 == (True, False)
    assert await t3 == (True, False)

    await follow_up.finalize_follow_up_capture(
        c2, activated=False, consumed_marked=True
    )
    await follow_up.finalize_follow_up_capture(
        c3, activated=False, consumed_marked=True
    )
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}


@pytest.mark.asyncio
async def test_media_follow_up_defers_and_blocks_later_text_from_jumping_ahead():
    e1 = _make_event("initial", message_id="m1")
    turn1 = _make_fake_turn(e1, turn_id="t1")

    e2_img = _make_event("", [Image(file="cat.png")], message_id="m2")
    e3_txt = _make_event("what is in the image I just sent?", message_id="m3")
    e4_txt = _make_event("also translate it", message_id="m4")

    c2 = follow_up.try_capture_follow_up(e2_img, turn1)
    c3 = follow_up.try_capture_follow_up(e3_txt, turn1)
    c4 = follow_up.try_capture_follow_up(e4_txt, turn1)

    assert c2 is not None and c2.receipt is None and c2.monitor_task is None
    assert c3 is not None and c3.receipt is None and c3.monitor_task is None
    assert c4 is not None and c4.receipt is None and c4.monitor_task is None
    turn1.steer.assert_not_called()

    order: list[str] = []

    async def run_slot(
        name: str, capture: follow_up.FollowUpCapture, gate: asyncio.Event
    ):
        consumed, activated = await follow_up.prepare_follow_up_capture(capture)
        try:
            assert not consumed and activated
            order.append(f"start:{name}")
            await gate.wait()
            order.append(f"end:{name}")
        finally:
            await follow_up.finalize_follow_up_capture(
                capture, activated=activated, consumed_marked=consumed
            )

    gate2, gate3, gate4 = asyncio.Event(), asyncio.Event(), asyncio.Event()
    task2 = asyncio.create_task(run_slot("img", c2, gate2))
    task3 = asyncio.create_task(run_slot("txt1", c3, gate3))
    task4 = asyncio.create_task(run_slot("txt2", c4, gate4))

    await asyncio.sleep(0)
    assert order == ["start:img"]

    gate2.set()
    await task2
    await asyncio.sleep(0)
    assert order == ["start:img", "end:img", "start:txt1"]

    gate3.set()
    await task3
    await asyncio.sleep(0)
    assert order == ["start:img", "end:img", "start:txt1", "end:txt1", "start:txt2"]

    gate4.set()
    await task4
    assert order == [
        "start:img",
        "end:img",
        "start:txt1",
        "end:txt1",
        "start:txt2",
        "end:txt2",
    ]
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("text_consumed", [True, False])
async def test_mixed_text_then_image_then_text_preserves_exact_order(text_consumed):
    e1 = _make_event("initial", message_id="m1")
    turn1 = _make_fake_turn(e1, turn_id="t1")

    e2_txt = _make_event("steer before image", message_id="m2")
    e3_img = _make_event("", [Image(file="pic.png")], message_id="m3")
    e4_txt = _make_event("after image", message_id="m4")

    c2 = follow_up.try_capture_follow_up(e2_txt, turn1)
    c3 = follow_up.try_capture_follow_up(e3_img, turn1)
    c4 = follow_up.try_capture_follow_up(e4_txt, turn1)

    assert c2 is not None and c2.receipt is not None
    assert c3 is not None and c3.receipt is None
    assert c4 is not None and c4.receipt is None
    assert turn1.steer.call_count == 1

    order: list[str] = []

    async def drive(name: str, capture: follow_up.FollowUpCapture):
        consumed, activated = await follow_up.prepare_follow_up_capture(capture)
        try:
            if consumed:
                order.append(f"consumed:{name}")
                return
            order.append(f"run:{name}")
        finally:
            await follow_up.finalize_follow_up_capture(
                capture, activated=activated, consumed_marked=consumed
            )

    t2 = asyncio.create_task(drive("txt1", c2))
    t3 = asyncio.create_task(drive("img", c3))
    t4 = asyncio.create_task(drive("txt2", c4))
    await asyncio.sleep(0)
    assert order == []

    c2.receipt.resolve(text_consumed)
    await asyncio.gather(t2, t3, t4)

    expected = (
        ["consumed:txt1", "run:img", "run:txt2"]
        if text_consumed
        else ["run:txt1", "run:img", "run:txt2"]
    )
    assert order == expected
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}


@pytest.mark.asyncio
async def test_barrier_releases_once_deferred_image_becomes_active_turn():
    e1 = _make_event("run 1", message_id="m1")
    turn1 = _make_fake_turn(e1, turn_id="t1")

    e2_img = _make_event("", [Image(file="chart.png")], message_id="m2")
    c2 = follow_up.try_capture_follow_up(e2_img, turn1)
    assert c2 is not None and c2.receipt is None
    assert await follow_up.prepare_follow_up_capture(c2) == (False, True)

    # Now turn 1 finished and e2_img itself is running as active turn 2,
    # with no later queued slot waiting behind it.
    turn2 = _make_fake_turn(e2_img, turn_id="t2")
    e3_txt = _make_event("only summarize column A", message_id="m3")
    c3 = follow_up.try_capture_follow_up(e3_txt, turn2)
    assert c3 is not None and c3.receipt is not None
    turn2.steer.assert_called_once()

    c3.receipt.resolve(True)
    assert await follow_up.prepare_follow_up_capture(c3) == (True, False)
    await follow_up.finalize_follow_up_capture(
        c3, activated=False, consumed_marked=True
    )
    await follow_up.finalize_follow_up_capture(
        c2, activated=True, consumed_marked=False
    )
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}


@pytest.mark.asyncio
async def test_barrier_still_blocks_steering_turn2_when_earlier_text_is_waiting():
    e1 = _make_event("run 1", message_id="m1")
    turn1 = _make_fake_turn(e1, turn_id="t1")

    e2_img = _make_event("", [Image(file="chart.png")], message_id="m2")
    e3_txt = _make_event("queued text", message_id="m3")
    c2 = follow_up.try_capture_follow_up(e2_img, turn1)
    c3 = follow_up.try_capture_follow_up(e3_txt, turn1)
    assert c2 is not None and c3 is not None
    assert await follow_up.prepare_follow_up_capture(c2) == (False, True)

    # e2_img is now running as turn2, while e3_txt is still queued behind it.
    turn2 = _make_fake_turn(e2_img, turn_id="t2")
    e4_txt = _make_event("later text must not jump ahead of e3", message_id="m4")
    c4 = follow_up.try_capture_follow_up(e4_txt, turn2)
    assert c4 is not None and c4.receipt is None
    turn2.steer.assert_not_called()

    await follow_up.finalize_follow_up_capture(
        c2, activated=True, consumed_marked=False
    )
    assert await follow_up.prepare_follow_up_capture(c3) == (False, True)
    await follow_up.finalize_follow_up_capture(
        c3, activated=True, consumed_marked=False
    )
    assert await follow_up.prepare_follow_up_capture(c4) == (False, True)
    await follow_up.finalize_follow_up_capture(
        c4, activated=True, consumed_marked=False
    )
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}


@pytest.mark.asyncio
async def test_transition_gap_and_pending_session_turns_block_reordering():
    e1 = _make_event("run 1", message_id="m1")
    turn1 = _make_fake_turn(e1, turn_id="t1")

    # Gap case: turn1 just finished (active=None) while deferred e2 is still active.
    e2_file = _make_event("", [File(name="a.pdf", file="a.pdf")], message_id="m2")
    c2 = follow_up.try_capture_follow_up(e2_file, turn1)
    assert c2 is not None
    assert await follow_up.prepare_follow_up_capture(c2) == (False, True)

    e3_txt = _make_event("summarize the file", message_id="m3")
    c3 = follow_up.try_capture_follow_up(e3_txt, None)
    assert c3 is not None and c3.receipt is None

    woke = asyncio.Event()

    async def wait_e3():
        consumed, activated = await follow_up.prepare_follow_up_capture(c3)
        woke.set()
        await follow_up.finalize_follow_up_capture(
            c3, activated=activated, consumed_marked=consumed
        )

    t3 = asyncio.create_task(wait_e3())
    await asyncio.sleep(0)
    assert not woke.is_set()

    await follow_up.finalize_follow_up_capture(
        c2, activated=True, consumed_marked=False
    )
    await asyncio.wait_for(t3, 1)
    assert woke.is_set()
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}

    # Pending session turn case: another turn is already queued on session._turns.
    turn_with_pending = _make_fake_turn(e1, turn_id="t-pending", pending_turn_count=1)
    e4_txt = _make_event("do not jump ahead of queued turn", message_id="m4")
    c4 = follow_up.try_capture_follow_up(e4_txt, turn_with_pending)
    assert c4 is not None and c4.receipt is None
    turn_with_pending.steer.assert_not_called()
    assert await follow_up.prepare_follow_up_capture(c4) == (False, True)
    await follow_up.finalize_follow_up_capture(
        c4, activated=True, consumed_marked=False
    )
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}


@pytest.mark.asyncio
async def test_cancellation_and_errors_release_slots_without_deadlock_or_leak():
    e1 = _make_event("run 1", message_id="m1")
    turn1 = _make_fake_turn(e1, turn_id="t1")

    e2 = _make_event("", [Image(file="a.png")], message_id="m2")
    e3 = _make_event("middle waiter", message_id="m3")
    e4 = _make_event("last waiter", message_id="m4")
    c2 = follow_up.try_capture_follow_up(e2, turn1)
    c3 = follow_up.try_capture_follow_up(e3, turn1)
    c4 = follow_up.try_capture_follow_up(e4, turn1)
    assert c2 is not None and c3 is not None and c4 is not None

    assert await follow_up.prepare_follow_up_capture(c2) == (False, True)

    async def waiter(capture: follow_up.FollowUpCapture):
        consumed = activated = False
        try:
            consumed, activated = await follow_up.prepare_follow_up_capture(capture)
            return True
        finally:
            await follow_up.finalize_follow_up_capture(
                capture, activated=activated, consumed_marked=consumed
            )

    t3 = asyncio.create_task(waiter(c3))
    t4 = asyncio.create_task(waiter(c4))
    await asyncio.sleep(0)

    # Cancel middle waiter while sleeping on condition.wait()
    t3.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t3

    # Releasing head slot must wake e4 cleanly past cancelled e3.
    await follow_up.finalize_follow_up_capture(
        c2, activated=True, consumed_marked=False
    )
    assert await asyncio.wait_for(t4, 1) is True
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}


@pytest.mark.asyncio
async def test_out_of_order_cancellation_and_monitor_failure_clean_up_state():
    e1 = _make_event("run 1", message_id="m1")
    turn1 = _make_fake_turn(e1, turn_id="t1")

    c2 = follow_up.try_capture_follow_up(_make_event("", [Image(file="1.png")]), turn1)
    c3 = follow_up.try_capture_follow_up(_make_event("two"), turn1)
    c4 = follow_up.try_capture_follow_up(_make_event("three"), turn1)
    assert c2 is not None and c3 is not None and c4 is not None

    # Finalize in reverse order (as happens when later tasks cancel before head).
    await follow_up.finalize_follow_up_capture(
        c4, activated=False, consumed_marked=False
    )
    await follow_up.finalize_follow_up_capture(
        c3, activated=False, consumed_marked=False
    )
    await follow_up.finalize_follow_up_capture(
        c2, activated=False, consumed_marked=False
    )
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}

    # Even if monitor_task raises unexpectedly, finalize still releases its order slot.
    e5 = _make_event("five")
    c5 = follow_up.try_capture_follow_up(e5, turn1)
    assert c5 is not None

    async def boom_on_cancel():
        try:
            await asyncio.Event().wait()
        finally:
            raise RuntimeError("monitor error")

    if c5.monitor_task is not None:
        c5.monitor_task.cancel()
        try:
            await c5.monitor_task
        except asyncio.CancelledError:
            pass
    c5.monitor_task = asyncio.create_task(boom_on_cancel())
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="monitor error"):
        await follow_up.finalize_follow_up_capture(
            c5, activated=False, consumed_marked=False
        )
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}


def test_stopped_and_targeted_wakeup_events_skip_capture():
    e1 = _make_event("run 1", message_id="m1")
    turn1 = _make_fake_turn(e1, turn_id="t1")

    stopped = _make_event("stopped")
    stopped.stop_event()
    assert follow_up.try_capture_follow_up(stopped, turn1) is None

    stop_requested = _make_event("stop requested")
    stop_requested.set_extra("agent_stop_requested", True)
    assert follow_up.try_capture_follow_up(stop_requested, turn1) is None

    targeted_wakeup = AgentWakeupEvent(
        context=SimpleNamespace(),
        session=MessageSession.from_str(e1.unified_msg_origin),
        platform_meta=PlatformMetadata(id="target", name="aiocqhttp", description="T"),
        prompt="child result",
        source="background_task",
        agent_session=AgentSessionRef("astrbot", "conv-1"),
    )
    assert follow_up.try_capture_follow_up(targeted_wakeup, turn1) is None
    turn1.steer.assert_not_called()
    assert follow_up._FOLLOW_UP_ORDER_STATE == {}


# ---------------------------------------------------------------------------
# End-to-end integration tests with real pipeline, runtime, and runner
# ---------------------------------------------------------------------------


async def _build_e2e_harness(monkeypatch, *, modalities: list[str] | None = None):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["provider_settings"]["streaming_response"] = False
    config["provider_settings"]["wake_prefix"] = ""
    config["provider_settings"]["datetime_system_prompt"] = False
    config["provider_settings"]["identifier"] = False
    config["platform_settings"]["unique_session"] = False
    config["admins_id"] = []

    conversation = SimpleNamespace(cid="conversation", history="[]", token_usage=0)
    queue: asyncio.Queue = asyncio.Queue()
    metadata = PlatformMetadata(id="target", name="aiocqhttp", description="Target")

    state = SimpleNamespace(
        requests=[],
        responses=[],
        tool_entered=asyncio.Event(),
        tool_gate=asyncio.Event(),
        llm_entered=asyncio.Event(),
        llm_gate=asyncio.Event(),
        use_tool_on_first_call=False,
    )
    state.tool_gate.set()
    state.llm_gate.set()

    class WaitTool(FunctionTool):
        def __init__(self):
            super().__init__(
                name="slow_lookup",
                description="Slow lookup tool for testing steering and media follow-ups",
                parameters={"type": "object", "properties": {}},
            )

        async def call(self, context):
            state.tool_entered.set()
            await state.tool_gate.wait()
            return "lookup_ok"

    tool_mgr = FunctionToolManager()

    async def save(*args, **kwargs):
        conversation.history = json.dumps(kwargs["history"])

    async def get_conversation(umo, cid):
        conversation.user_id = umo
        return conversation

    context = SimpleNamespace(
        get_event_queue=lambda: queue,
        get_platform_inst=lambda _: SimpleNamespace(meta=lambda: metadata),
        get_config=lambda **_: config,
        locale=lambda umo=None: "en-US",
        get_locale=AsyncMock(return_value="en-US"),
        astrbot_config_mgr=SimpleNamespace(
            _create_message_config=lambda _: (copy.deepcopy(config), frozenset())
        ),
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value=conversation.cid),
            get_conversation=AsyncMock(side_effect=get_conversation),
            update_conversation=AsyncMock(side_effect=save),
        ),
        get_using_tts_provider_async=AsyncMock(return_value=None),
        get_llm_tool_manager=lambda: tool_mgr,
        send_message=AsyncMock(return_value=True),
    )

    async def read_history(cid):
        event = current_message_event.get()
        umo = event.unified_msg_origin if event else conversation.user_id
        record = await context.conversation_manager.get_conversation(umo, cid)
        if record is None:
            return None
        return SimpleNamespace(
            **vars(record),
            conversation_id=record.cid,
            umo=record.user_id,
            content=json.loads(record.history),
        )

    async def read_execution(cid):
        record = await read_history(cid)
        return (record, None) if record is not None else None

    context.conversation_manager.db = SimpleNamespace(
        get_conversation_by_id=AsyncMock(side_effect=read_history),
        conversation_store=SimpleNamespace(
            get_metadata=AsyncMock(side_effect=read_history),
            read_for_execution=AsyncMock(side_effect=read_execution),
        ),
    )
    context.conversation_manager.to_legacy_conversation = lambda record: record

    async def respond(**kwargs):
        call_index = len(state.requests)
        state.requests.append(copy.deepcopy(kwargs["contexts"]))
        state.llm_entered.set()
        if call_index == 0 and state.use_tool_on_first_call:
            return LLMResponse(
                role="assistant",
                tools_call_name=["slow_lookup"],
                tools_call_ids=["call-1"],
                tools_call_args=[{}],
            )
        if call_index == 0:
            await state.llm_gate.wait()
        reply = f"Reply {call_index + 1}"
        state.responses.append(reply)
        return LLMResponse(role="assistant", completion_text=reply)

    provider = SimpleNamespace(
        provider_config={
            "id": "offline-vision",
            "modalities": modalities or ["text", "image"],
        },
        get_model=lambda: "offline-vision",
        meta=lambda: SimpleNamespace(type="test"),
        text_chat=respond,
    )

    from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor

    async def build(
        *, event, plugin_context, config, req=None, collected_input=None, **kwargs
    ):
        prepared = await prepare_request(
            event, plugin_context, config, provider, req, collected_input
        )
        assert prepared is not None
        prepared.request.func_tool = ToolSet(tools=[WaitTool()])
        runner = AgentRunner()
        await runner.reset(
            provider=provider,
            request=prepared.request,
            run_context=ContextWrapper(
                context=SimpleNamespace(
                    event=event,
                    context=plugin_context,
                    send_to_user=True,
                    _output_turn=None,
                )
            ),
            tool_executor=FunctionToolExecutor(),
            agent_hooks=BaseAgentRunHooks(),
            streaming=False,
        )
        return MainAgentBuildResult(runner, prepared.request, provider)

    monkeypatch.setattr(native_builder, "build_main_agent", build)
    monkeypatch.setattr(native_session, "record_agent_stats", AsyncMock())
    monkeypatch.setattr(native_session.Metric, "upload", AsyncMock())

    subagents = MagicMock()
    subagents.store.find_native_conversation.return_value = None
    native = AstrAgentRuntime(context, agent_configs=MagicMock(), subagents=subagents)
    scheduler = PipelineScheduler(
        PipelineContext(
            config,
            SimpleNamespace(context=context),
            "profile",
            agent_runtimes={"astrbot": native},
        )
    )
    await scheduler.initialize()
    bus = EventBus(
        queue,
        {"profile": scheduler},
        SimpleNamespace(get_conf_info=lambda _: {"id": "profile"}),
    )
    dispatcher = asyncio.create_task(bus.dispatch())

    async def drain():
        while not queue.empty() or bus._pending_tasks:
            await asyncio.sleep(0)
            await asyncio.gather(*list(bus._pending_tasks), return_exceptions=True)

    async def close():
        dispatcher.cancel()
        pending = [dispatcher, *bus._pending_tasks]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await native.close()

    state.queue = queue
    state.drain = drain
    state.close = close
    state.conversation = conversation
    state.native = native
    return state


def _extract_request_summary(contexts: list[dict]) -> tuple[list[str], int]:
    texts: list[str] = []
    image_count = 0
    for message in contexts:
        content = message.get("content", "")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for part in content:
                if part.get("type") == "text":
                    texts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    image_count += 1
    return texts, image_count


@pytest.mark.asyncio
async def test_e2e_pure_image_during_active_run_is_not_collapsed_and_blocks_text_reordering(
    monkeypatch, tmp_path
):
    img_path = tmp_path / "cat.png"
    PILImage.new("RGB", (8, 8), "orange").save(img_path)

    harness = await _build_e2e_harness(monkeypatch)
    try:
        harness.use_tool_on_first_call = True
        harness.tool_gate.clear()

        first = _make_event("Run first task", message_id="m1")
        await harness.queue.put(first)
        await asyncio.wait_for(harness.tool_entered.wait(), 3)

        # User sends a pure image while Run 1 is mid-tool, then immediately sends a
        # plain-text follow-up referencing that image before Run 1 completes.
        image_event = _make_event(
            "", [Image.fromFileSystem(str(img_path))], message_id="m2"
        )
        follow_text = _make_event(
            "What cat is in the image I just sent?", message_id="m3"
        )

        await harness.queue.put(image_event)
        for _ in range(10):
            await asyncio.sleep(0)
        await harness.queue.put(follow_text)
        for _ in range(10):
            await asyncio.sleep(0)

        # Release Run 1's tool and let all turns settle.
        harness.tool_gate.set()
        await asyncio.wait_for(harness.drain(), 5)

        assert image_event.get_extra("_follow_up_captured") is None
        assert follow_text.get_extra("_follow_up_captured") is None

        # Expect 4 LLM calls total:
        # 0: Run 1 initial -> tool call
        # 1: Run 1 after tool result (must NOT contain "[图片]" or follow_text!)
        # 2: Run 2 with the REAL image attachment
        # 3: Run 3 with follow_text AFTER Run 2's image + reply are in history
        assert len(harness.requests) == 4

        run1_post_tool_texts, run1_images = _extract_request_summary(
            harness.requests[1]
        )
        assert run1_images == 0
        assert "[图片]" not in "\n".join(run1_post_tool_texts)
        assert "What cat is in the image I just sent?" not in "\n".join(
            run1_post_tool_texts
        )

        run2_texts, run2_images = _extract_request_summary(harness.requests[2])
        assert run2_images == 1
        assert "What cat is in the image I just sent?" not in "\n".join(run2_texts)

        run3_texts, run3_images = _extract_request_summary(harness.requests[3])
        assert run3_images == 1  # Turn 2's image is already committed in history
        joined_run3 = "\n".join(run3_texts)
        assert "Reply 3" in joined_run3  # Turn 2's assistant reply precedes Turn 3
        assert "What cat is in the image I just sent?" in joined_run3

        assert follow_up._FOLLOW_UP_ORDER_STATE == {}
    finally:
        await harness.close()


@pytest.mark.asyncio
async def test_e2e_mixed_text_and_image_during_active_run_preserves_both(
    monkeypatch, tmp_path
):
    img_path = tmp_path / "diagram.png"
    PILImage.new("RGB", (8, 8), "green").save(img_path)

    harness = await _build_e2e_harness(monkeypatch)
    try:
        harness.llm_gate.clear()
        first = _make_event("Initial turn", message_id="m1")
        await harness.queue.put(first)
        await asyncio.wait_for(harness.llm_entered.wait(), 3)

        mixed_event = _make_event(
            "Check this diagram",
            [Plain("Check this diagram"), Image.fromFileSystem(str(img_path))],
            message_id="m2",
        )
        await harness.queue.put(mixed_event)
        for _ in range(10):
            await asyncio.sleep(0)

        harness.llm_gate.set()
        await asyncio.wait_for(harness.drain(), 5)

        assert mixed_event.get_extra("_follow_up_captured") is None
        assert len(harness.requests) == 2

        run2_texts, run2_images = _extract_request_summary(harness.requests[1])
        assert run2_images == 1
        assert "Check this diagram" in "\n".join(run2_texts)
        assert follow_up._FOLLOW_UP_ORDER_STATE == {}
    finally:
        await harness.close()


@pytest.mark.asyncio
async def test_e2e_quoted_reply_during_active_run_preserves_quoted_context(monkeypatch):
    harness = await _build_e2e_harness(monkeypatch)
    try:
        harness.llm_gate.clear()
        first = _make_event("Initial question", message_id="m1")
        await harness.queue.put(first)
        await asyncio.wait_for(harness.llm_entered.wait(), 3)

        reply_event = _make_event(
            "Explain this part",
            [
                Reply(
                    id="orig-1",
                    sender_nickname="Bob",
                    message_str="Secret formula X=42",
                    chain=[Plain("Secret formula X=42")],
                ),
                Plain("Explain this part"),
            ],
            message_id="m2",
        )
        await harness.queue.put(reply_event)
        for _ in range(10):
            await asyncio.sleep(0)

        harness.llm_gate.set()
        await asyncio.wait_for(harness.drain(), 5)

        assert reply_event.get_extra("_follow_up_captured") is None
        assert len(harness.requests) == 2

        run2_texts, _ = _extract_request_summary(harness.requests[1])
        joined_run2 = "\n".join(run2_texts)
        assert "<Quoted Message>" in joined_run2
        assert "Secret formula X=42" in joined_run2
        assert "Explain this part" in joined_run2
        assert follow_up._FOLLOW_UP_ORDER_STATE == {}
    finally:
        await harness.close()


@pytest.mark.asyncio
async def test_e2e_plain_text_follow_up_continues_to_steer_active_turn(monkeypatch):
    harness = await _build_e2e_harness(monkeypatch)
    try:
        harness.llm_gate.clear()
        first = _make_event("Start working", message_id="m1")
        await harness.queue.put(first)
        await asyncio.wait_for(harness.llm_entered.wait(), 3)

        steer_event = _make_event("Answer in concise bullets", message_id="m2")
        await harness.queue.put(steer_event)
        for _ in range(10):
            await asyncio.sleep(0)

        harness.llm_gate.set()
        await asyncio.wait_for(harness.drain(), 5)

        # Steering was consumed inside Turn 1 (2nd LLM call in the same turn).
        assert steer_event.get_extra("_follow_up_captured") is not None
        assert len(harness.requests) == 2
        run1_step2_texts, _ = _extract_request_summary(harness.requests[1])
        assert "Answer in concise bullets" in "\n".join(run1_step2_texts)
        assert follow_up._FOLLOW_UP_ORDER_STATE == {}
    finally:
        await harness.close()


@pytest.mark.asyncio
async def test_e2e_stop_while_deferred_skips_queued_turns_and_cleans_up(
    monkeypatch, tmp_path
):
    img_path = tmp_path / "stop_test.png"
    PILImage.new("RGB", (4, 4), "blue").save(img_path)

    harness = await _build_e2e_harness(monkeypatch)
    try:
        harness.llm_gate.clear()
        first = _make_event("Long run", message_id="m1")
        await harness.queue.put(first)
        await asyncio.wait_for(harness.llm_entered.wait(), 3)

        img_event = _make_event(
            "", [Image.fromFileSystem(str(img_path))], message_id="m2"
        )
        txt_event = _make_event("follow up after image", message_id="m3")
        txt_typing = AsyncMock()
        txt_event.send_typing = txt_typing

        await harness.queue.put(img_event)
        for _ in range(10):
            await asyncio.sleep(0)
        await harness.queue.put(txt_event)
        for _ in range(10):
            await asyncio.sleep(0)

        # User issues /stop while Run 1 is active and img_event + txt_event are waiting.
        active_event_registry.request_agent_stop_all(first.unified_msg_origin)
        harness.llm_gate.set()
        await asyncio.wait_for(harness.drain(), 5)

        # Neither queued turn should have executed an LLM request, and txt_event
        # must not have emitted a spurious typing indicator after being stopped.
        assert len(harness.requests) == 1
        txt_typing.assert_not_awaited()
        assert follow_up._FOLLOW_UP_ORDER_STATE == {}
    finally:
        await harness.close()
