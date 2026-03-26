"""Tests for pipeline scheduler — each stage executes exactly once.

Regression test for the bug where stages after a generator (onion-model)
stage were executed twice: once via the recursive _process_stages call
inside the generator, and again by the outer for-loop.
"""

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.pipeline.stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


# ── Helper stages ────────────────────────────────────────


class CounterStage(Stage):
    """普通 stage，记录 process() 被调用的次数。"""

    def __init__(self):
        self.call_count = 0

    async def initialize(self, ctx: PipelineContext) -> None:
        pass

    async def process(self, event) -> None:
        self.call_count += 1


class GeneratorStage(Stage):
    """洋葱模型 stage（含 yield），模拟 ProcessStage。"""

    def __init__(self):
        self.call_count = 0

    async def initialize(self, ctx: PipelineContext) -> None:
        pass

    async def process(self, event) -> AsyncGenerator[None, None]:
        self.call_count += 1
        yield  # 前置处理完成，等待后续 stage


class NoYieldGeneratorStage(Stage):
    """Generator stage 但条件不满足时不 yield，模拟 ContentSafetyCheckStage 通过的情况。"""

    def __init__(self):
        self.call_count = 0

    async def initialize(self, ctx: PipelineContext) -> None:
        pass

    async def process(self, event) -> AsyncGenerator[None, None]:
        self.call_count += 1
        # 条件不满足，直接 return，不 yield
        return
        yield  # noqa: RET504 — 使函数成为 async generator


# ── Helper: build event & scheduler ──────────────────────


class ConcreteAstrMessageEvent(AstrMessageEvent):
    async def send(self, message):
        await super().send(message)


def _make_event():
    meta = PlatformMetadata(name="test", description="", id="test_id")
    msg = AstrBotMessage()
    msg.type = MessageType.FRIEND_MESSAGE
    msg.self_id = "bot1"
    msg.session_id = "sess1"
    msg.message_id = "msg1"
    msg.sender = MessageMember(user_id="u1", nickname="Alice")
    msg.message = [Plain(text="hello")]
    msg.message_str = "hello"
    msg.raw_message = None
    return ConcreteAstrMessageEvent(
        message_str="hello",
        message_obj=msg,
        platform_meta=meta,
        session_id="sess1",
    )


def _make_scheduler(stages):
    """Build a PipelineScheduler with manually injected stages."""
    ctx = MagicMock(spec=PipelineContext)
    ctx.astrbot_config = {}
    scheduler = object.__new__(PipelineScheduler)
    scheduler.ctx = ctx
    scheduler.stages = stages
    return scheduler


# ── Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stages_after_generator_execute_once():
    """generator stage 后的普通 stage 只执行一次。"""
    gen_stage = GeneratorStage()
    counter1 = CounterStage()
    counter2 = CounterStage()

    scheduler = _make_scheduler([gen_stage, counter1, counter2])
    event = _make_event()
    await scheduler._process_stages(event)

    assert gen_stage.call_count == 1
    assert counter1.call_count == 1
    assert counter2.call_count == 1


@pytest.mark.asyncio
async def test_nested_generators_execute_once():
    """两个 generator stage 嵌套时，最后的普通 stage 仍只执行一次。"""
    gen1 = GeneratorStage()
    gen2 = GeneratorStage()
    counter = CounterStage()

    scheduler = _make_scheduler([gen1, gen2, counter])
    event = _make_event()
    await scheduler._process_stages(event)

    assert gen1.call_count == 1
    assert gen2.call_count == 1
    assert counter.call_count == 1


@pytest.mark.asyncio
async def test_all_plain_stages_execute_once():
    """纯普通 stage 流水线，每个只执行一次。"""
    stages = [CounterStage() for _ in range(4)]

    scheduler = _make_scheduler(stages)
    event = _make_event()
    await scheduler._process_stages(event)

    for i, s in enumerate(stages):
        assert s.call_count == 1, f"stage[{i}] executed {s.call_count} times"


@pytest.mark.asyncio
async def test_generator_between_plain_stages():
    """普通 → generator → 普通 → 普通，所有 stage 只执行一次。"""
    plain_before = CounterStage()
    gen_stage = GeneratorStage()
    plain_after1 = CounterStage()
    plain_after2 = CounterStage()

    scheduler = _make_scheduler([plain_before, gen_stage, plain_after1, plain_after2])
    event = _make_event()
    await scheduler._process_stages(event)

    assert plain_before.call_count == 1
    assert gen_stage.call_count == 1
    assert plain_after1.call_count == 1
    assert plain_after2.call_count == 1


@pytest.mark.asyncio
async def test_generator_at_end_executes_once():
    """generator stage 在最末尾时也只执行一次。"""
    counter = CounterStage()
    gen_stage = GeneratorStage()

    scheduler = _make_scheduler([counter, gen_stage])
    event = _make_event()
    await scheduler._process_stages(event)

    assert counter.call_count == 1
    assert gen_stage.call_count == 1


@pytest.mark.asyncio
async def test_no_yield_generator_does_not_block_subsequent_stages():
    """Generator stage 未 yield（条件不满足直接 return）时，后续 stage 仍应执行。

    回归测试：ContentSafetyCheckStage 在内容安全通过时不 yield，
    后续的 ProcessStage / RespondStage 不应被跳过。
    """
    no_yield = NoYieldGeneratorStage()
    counter1 = CounterStage()
    counter2 = CounterStage()

    scheduler = _make_scheduler([no_yield, counter1, counter2])
    event = _make_event()
    await scheduler._process_stages(event)

    assert no_yield.call_count == 1
    assert counter1.call_count == 1
    assert counter2.call_count == 1


@pytest.mark.asyncio
async def test_no_yield_then_yield_generator():
    """未 yield 的 generator → 正常 yield 的 generator → 普通 stage，全部只执行一次。"""
    no_yield = NoYieldGeneratorStage()
    gen = GeneratorStage()
    counter = CounterStage()

    scheduler = _make_scheduler([no_yield, gen, counter])
    event = _make_event()
    await scheduler._process_stages(event)

    assert no_yield.call_count == 1
    assert gen.call_count == 1
    assert counter.call_count == 1
