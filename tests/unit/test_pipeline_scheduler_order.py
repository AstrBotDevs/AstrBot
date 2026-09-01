import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.pipeline.stage import Stage
from astrbot.core.pipeline.stage_order import STAGES_ORDER
from astrbot.core.utils.active_event_registry import ActiveEventRegistry


class PipelineEvent:
    def __init__(self) -> None:
        self.stopped = False
        self.trace: list[str] = []
        self.requires_empty_completion = False
        self.unified_msg_origin = "webchat:FriendMessage:pipeline"
        self.cleaned = False
        self._extras: dict[str, object] = {}
        self.sent_none = False

    def is_stopped(self) -> bool:
        return self.stopped

    def stop_event(self) -> None:
        self.stopped = True

    def cleanup_temporary_local_files(self) -> None:
        self.cleaned = True

    def get_platform_id(self) -> str:
        return "webchat"

    def get_message_outline(self) -> str:
        return "hi"

    def get_extra(self, key: str | None = None, default=None):
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def set_extra(self, key, value) -> None:
        self._extras[key] = value

    async def send(self, message) -> None:
        if message is None:
            self.sent_none = True


class OnionStage(Stage):
    async def initialize(self, ctx) -> None:
        return None

    async def process(self, event: PipelineEvent):
        event.trace.append("pre")
        yield
        event.trace.append("post")


class TraceStage(Stage):
    def __init__(self, label: str, *, stop: bool = False) -> None:
        self.label = label
        self.stop = stop

    async def initialize(self, ctx) -> None:
        return None

    async def process(self, event: PipelineEvent) -> None:
        event.trace.append(self.label)
        if self.stop:
            event.stop_event()


class CancelStage(Stage):
    async def initialize(self, ctx) -> None:
        return None

    async def process(self, event: PipelineEvent) -> None:
        event.trace.append("cancel")
        raise asyncio.CancelledError


def _scheduler(stages: list[Stage]) -> PipelineScheduler:
    ctx = SimpleNamespace(
        execution_context=SimpleNamespace(
            active_event_registry=ActiveEventRegistry(),
        )
    )
    scheduler = PipelineScheduler(MagicMock())
    scheduler.ctx = ctx  # type: ignore[assignment]
    scheduler.stages = stages
    return scheduler


def test_builtin_stage_order_matches_stage_order_constant():
    from astrbot.core.pipeline.bootstrap import builtin_stage_classes

    assert tuple(cls.__name__ for cls in builtin_stage_classes()) == STAGES_ORDER


@pytest.mark.asyncio
async def test_pipeline_stops_propagation_but_finishes_onion_post():
    scheduler = _scheduler(
        [OnionStage(), TraceStage("middle", stop=True), TraceStage("late")]
    )
    event = PipelineEvent()

    await scheduler._process_stages(event)

    assert "pre" in event.trace
    assert "middle" in event.trace
    assert "late" not in event.trace
    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_pipeline_execute_reraises_cancelled_error_and_unregisters():
    scheduler = _scheduler([CancelStage()])
    event = PipelineEvent()
    registry = scheduler.ctx.execution_context.active_event_registry

    with pytest.raises(asyncio.CancelledError):
        await scheduler.execute(event)

    assert event.cleaned is True
    assert event.unified_msg_origin not in registry._events


@pytest.mark.asyncio
async def test_pipeline_skips_empty_completion_when_coalesce_defers_it():
    scheduler = _scheduler([TraceStage("only")])
    event = PipelineEvent()
    event.requires_empty_completion = True
    event.set_extra("skip_empty_completion", True)

    await scheduler.execute(event)

    assert event.sent_none is False


@pytest.mark.asyncio
async def test_pipeline_sends_empty_completion_for_webchat_when_not_skipped():
    scheduler = _scheduler([TraceStage("only")])
    event = PipelineEvent()
    event.requires_empty_completion = True

    await scheduler.execute(event)

    assert event.sent_none is True
