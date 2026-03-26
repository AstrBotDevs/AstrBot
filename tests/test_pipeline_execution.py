"""流水线执行次数测试。

验证洋葱模型阶段后的普通阶段只执行一次，
多层洋葱嵌套不重复执行，
未挂起的异步生成器阶段不阻断后续执行。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.pipeline.scheduler import PipelineScheduler


def _make_normal_stage(name: str, counter: dict):
    """创建普通（非洋葱）阶段"""
    stage = MagicMock()
    stage.__class__ = type(name, (), {})
    stage.__class__.__name__ = name
    counter[name] = 0

    async def process(event):
        counter[name] += 1

    stage.process = process
    return stage


def _make_onion_stage(name: str, counter: dict):
    """创建洋葱（generator）阶段"""
    stage = MagicMock()
    stage.__class__ = type(name, (), {})
    stage.__class__.__name__ = name
    counter[f"{name}_pre"] = 0
    counter[f"{name}_post"] = 0

    async def process(event):
        counter[f"{name}_pre"] += 1
        yield
        counter[f"{name}_post"] += 1

    stage.process = process
    return stage


def _make_non_suspending_generator_stage(name: str, counter: dict):
    """创建不 yield 的异步生成器阶段（立即返回）"""
    stage = MagicMock()
    stage.__class__ = type(name, (), {})
    stage.__class__.__name__ = name
    counter[name] = 0

    async def process(event):
        counter[name] += 1
        return
        yield  # noqa: RET504 — 使 process 成为 async generator 但永不 yield

    stage.process = process
    return stage


def _make_event():
    event = MagicMock()
    event.is_stopped.return_value = False
    return event


def _make_scheduler_with_stages(stages):
    """创建带有指定 stages 的 PipelineScheduler（绕过正常初始化）"""
    scheduler = object.__new__(PipelineScheduler)
    scheduler.stages = stages
    scheduler.ctx = MagicMock()
    scheduler.pre_ack_emoji_mgr = MagicMock()
    scheduler.pre_ack_emoji_mgr.add_emoji = AsyncMock(return_value=None)
    scheduler.pre_ack_emoji_mgr.remove_emoji = AsyncMock()
    return scheduler


class TestOnionThenNormalExecutesOnce:
    """洋葱阶段后的普通阶段只执行一次"""

    @pytest.mark.asyncio
    async def test_normal_after_single_onion(self):
        counter = {}
        onion = _make_onion_stage("Onion", counter)
        normal = _make_normal_stage("Normal", counter)

        scheduler = _make_scheduler_with_stages([onion, normal])
        event = _make_event()

        await scheduler._process_stages(event)

        assert counter["Onion_pre"] == 1
        assert counter["Normal"] == 1
        assert counter["Onion_post"] == 1

    @pytest.mark.asyncio
    async def test_normal_after_two_onions(self):
        counter = {}
        onion1 = _make_onion_stage("Onion1", counter)
        onion2 = _make_onion_stage("Onion2", counter)
        normal = _make_normal_stage("Normal", counter)

        scheduler = _make_scheduler_with_stages([onion1, onion2, normal])
        event = _make_event()

        await scheduler._process_stages(event)

        assert counter["Onion1_pre"] == 1
        assert counter["Onion2_pre"] == 1
        assert counter["Normal"] == 1
        assert counter["Onion2_post"] == 1
        assert counter["Onion1_post"] == 1


class TestMultiOnionNesting:
    """多层洋葱嵌套不重复执行"""

    @pytest.mark.asyncio
    async def test_three_layer_onion_nesting(self):
        counter = {}
        stages = [
            _make_onion_stage("O1", counter),
            _make_onion_stage("O2", counter),
            _make_onion_stage("O3", counter),
            _make_normal_stage("Final", counter),
        ]

        scheduler = _make_scheduler_with_stages(stages)
        event = _make_event()

        await scheduler._process_stages(event)

        assert counter["O1_pre"] == 1
        assert counter["O2_pre"] == 1
        assert counter["O3_pre"] == 1
        assert counter["Final"] == 1
        assert counter["O3_post"] == 1
        assert counter["O2_post"] == 1
        assert counter["O1_post"] == 1


class TestNonSuspendingGeneratorStage:
    """未挂起的异步生成器阶段不阻断后续执行"""

    @pytest.mark.asyncio
    async def test_non_yielding_generator_does_not_block(self):
        counter = {}
        non_suspending = _make_non_suspending_generator_stage("NonSuspending", counter)
        normal = _make_normal_stage("After", counter)

        scheduler = _make_scheduler_with_stages([non_suspending, normal])
        event = _make_event()

        await scheduler._process_stages(event)

        assert counter["NonSuspending"] == 1
        assert counter["After"] == 1

    @pytest.mark.asyncio
    async def test_non_yielding_generator_between_onions(self):
        counter = {}
        onion = _make_onion_stage("Onion", counter)
        non_suspending = _make_non_suspending_generator_stage("NonSuspending", counter)
        normal = _make_normal_stage("Final", counter)

        scheduler = _make_scheduler_with_stages([onion, non_suspending, normal])
        event = _make_event()

        await scheduler._process_stages(event)

        assert counter["Onion_pre"] == 1
        assert counter["NonSuspending"] == 1
        assert counter["Final"] == 1
        assert counter["Onion_post"] == 1
