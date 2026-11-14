"""Protocol boundaries: typed snapshots, media round trips and presentation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from pydantic import ValidationError

from astrbot.core.agent.events import (
    MessageCompleted,
    ReasoningDelta,
    RuntimeEvent,
    RuntimeTokenUsage,
    TextDelta,
    ToolStarted,
    TurnResult,
)
from astrbot.core.agent.output import ExtensionOutput, PlainOutput, ReasoningOutput
from astrbot.core.agent.runtime import AgentInput, AgentPermissions, AgentSession
from astrbot.core.agent_output import present_turn
from astrbot.core.agent_output_content import chain_from_content, content_from_chain
from astrbot.core.message import components as Comp
from astrbot.core.message.message_event_result import MessageChain


class OutputSession(AgentSession):
    """A deterministic runtime with real independent turn scheduling."""

    async def execute_turn(self, turn):
        payload = ToolStarted(
            execution_id="execution",
            call_id="call",
            name="tool",
            arguments={"nested": {"value": 1}},
        )
        turn.emit(payload)
        payload.arguments["nested"]["value"] = 999
        return TurnResult(
            content=(
                PlainOutput(text="Final"),
                ExtensionOutput(namespace="test", name="nested", value={"value": 1}),
            )
        )

    async def history(self):
        return []


def input_for(session):
    event = MagicMock()
    event.unified_msg_origin = session.umo
    event.get_platform_name.return_value = "test"
    event.get_platform_id.return_value = "test"
    event.get_extra.return_value = None
    return AgentInput(event=event, permissions=AgentPermissions())


@pytest.mark.asyncio
async def test_runtime_events_are_replayable_detached_and_json_serializable():
    session = OutputSession("session", "test:FriendMessage:user")
    turn = await session.run_turn(input_for(session))
    result = await turn.result()  # Execution and settlement need no subscriber.
    first = [event async for event in turn.events()]
    first[1].payload.arguments["nested"]["value"] = 42
    result.content[1].value["value"] = 42
    second = [event async for event in turn.events()]
    assert second[1].payload.arguments == {"nested": {"value": 1}}
    assert (await turn.result()).content[1].value == {"value": 1}
    assert [event.event_id for event in first] == [event.event_id for event in second]
    for event in second:
        assert UUID(event.event_id)
        assert event.session.session_id == session.id
        assert event.turn_id == turn.id
        assert event.created_at.utcoffset().total_seconds() == 0
        assert RuntimeEvent.model_validate_json(event.model_dump_json()) == event
    assert second[-1].payload.result == await turn.result()
    with pytest.raises(RuntimeError, match="after turn.finished"):
        turn.emit(TextDelta(message_id="late", part_index=0, text="Late"))


def test_usage_distinguishes_unknown_zero_and_cache_subset():
    assert RuntimeTokenUsage().total_tokens is None
    usage = RuntimeTokenUsage(input_tokens=0, output_tokens=0, cached_input_tokens=0)
    assert usage.total_tokens == 0
    assert (
        RuntimeTokenUsage(
            input_tokens=10, output_tokens=2, cached_input_tokens=8
        ).total_tokens
        == 12
    )
    with pytest.raises(ValidationError):
        RuntimeTokenUsage(input_tokens=-1)
    with pytest.raises(ValidationError):
        ExtensionOutput(namespace="test", name="object", value=object())


@pytest.mark.parametrize(
    "component",
    [
        Comp.Plain("text"),
        Comp.Image(file="https://example.com/image.png"),
        Comp.File(name="report.pdf", file="/tmp/report.pdf"),
        Comp.Record(file="base64://YXVkaW8="),
        Comp.Video(file="/tmp/video.mp4"),
        Comp.At(qq="user"),
        Comp.Json(data={"html": "<div>GenUI</div>"}),
        Comp.Node(
            content=[Comp.Plain("Forwarded"), Comp.At(qq="user")],
            name="Author",
            uin="1",
        ),
    ],
)
def test_platform_content_round_trip_without_io(component):
    restored = chain_from_content(content_from_chain(MessageChain(chain=[component])))
    assert restored.chain[0].dict() == component.dict()


def test_unknown_extensions_fail_explicitly_at_presentation_boundary():
    content = (
        ExtensionOutput(namespace="vendor.example", name="unknown", value={"key": 1}),
    )
    assert content[0].value == {"key": 1}
    with pytest.raises(ValueError, match="Unsupported output extension"):
        chain_from_content(content)


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("reasoning_only_delta", [False, True])
async def test_message_snapshot_does_not_repeat_deltas_or_hide_unstreamed_text(
    streaming, reasoning_only_delta
):
    class MessageSession(OutputSession):
        async def execute_turn(self, turn):
            turn.emit(ReasoningDelta(message_id="reply", part_index=0, text="Thinking"))
            if not reasoning_only_delta:
                turn.emit(TextDelta(message_id="reply", part_index=1, text="Reply"))
            turn.emit(
                MessageCompleted(
                    message_id="reply",
                    content=(
                        ReasoningOutput(text="Thinking"),
                        PlainOutput(text="Reply"),
                    ),
                )
            )
            return TurnResult(content=(PlainOutput(text="Reply"),))

    session = MessageSession("session", "test:FriendMessage:user")
    turn = await session.run_turn(input_for(session))
    chains = [
        chain
        async for chain in present_turn(turn, streaming=streaming, show_reasoning=True)
    ]
    assert [
        chain.get_plain_text() for chain in chains if chain.type != "reasoning"
    ] == ["Reply"]
    assert [
        chain.get_plain_text() for chain in chains if chain.type == "reasoning"
    ] == (["Thinking"] if streaming else [])


@pytest.mark.asyncio
async def test_cancelled_turn_retains_already_reported_usage():
    """Cancelling later work cannot erase charges from a completed request."""
    from astrbot.core.agent.events import ExecutionMetrics, TurnUsage, UsageUpdated

    entered = asyncio.Event()
    usage = TurnUsage(
        source="requests",
        complete=False,
        tokens=RuntimeTokenUsage(input_tokens=12, output_tokens=3),
    )

    class ChargedSession(OutputSession):
        async def execute_turn(self, turn):
            turn.emit(UsageUpdated(usage=usage, metrics=ExecutionMetrics(steps=1)))
            entered.set()
            await asyncio.Event().wait()
            return TurnResult()

    session = ChargedSession("session", "test:FriendMessage:user")
    turn = await session.run_turn(input_for(session))
    await entered.wait()
    await turn.cancel()
    result = await turn.result()
    assert result.status == "cancelled"
    assert result.usage == usage
    assert result.metrics.steps == 1
    events = [event async for event in turn.events()]
    assert sum(event.type == "turn.finished" for event in events) == 1
    assert events[-1].payload.result == result
