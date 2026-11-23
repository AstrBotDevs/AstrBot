"""Exercise stage ordering, delegation and cleanup through the real scheduler."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.pipeline import scheduler as scheduler_module
from astrbot.core.pipeline.scheduler import PipelineScheduler


@pytest.fixture
def scheduler(monkeypatch):
    monkeypatch.setattr(scheduler_module, "registered_stages", [])
    monkeypatch.setattr(scheduler_module, "ensure_builtin_stages_registered", Mock())
    return PipelineScheduler(SimpleNamespace())


@pytest.fixture
def event():
    state = SimpleNamespace(stopped=False)
    state.is_stopped = lambda: state.stopped
    return state


@pytest.mark.asyncio
async def test_initialize_uses_configured_stage_order(monkeypatch):
    initialized = []

    class First:
        async def initialize(self, context):
            initialized.append(("first", context))

    class Second:
        async def initialize(self, context):
            initialized.append(("second", context))

    ensure = Mock()
    monkeypatch.setattr(scheduler_module, "ensure_builtin_stages_registered", ensure)
    monkeypatch.setattr(scheduler_module, "registered_stages", [Second, First])
    monkeypatch.setattr(scheduler_module, "STAGES_ORDER", ["First", "Second"])
    context = SimpleNamespace()
    scheduler = PipelineScheduler(context)

    assert scheduler.stages == []
    await scheduler.initialize()

    ensure.assert_called_once_with()
    assert scheduler.ctx is context
    assert [type(stage) for stage in scheduler.stages] == [First, Second]
    assert initialized == [("first", context), ("second", context)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "from_stage, expected", [(0, ["first", "second"]), (1, ["second"])]
)
async def test_coroutine_stages_execute_once_in_order(
    scheduler, event, from_stage, expected
):
    calls = []

    async def first(received):
        assert received is event
        calls.append("first")

    async def second(received):
        assert received is event
        calls.append("second")

    scheduler.stages = [SimpleNamespace(process=first), SimpleNamespace(process=second)]
    await scheduler._process_stages(event, from_stage=from_stage)
    assert calls == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("yield_count", [0, 1, 3])
async def test_generator_delegates_suffix_once_per_yield(scheduler, event, yield_count):
    calls = []

    async def parent(received):
        assert received is event
        try:
            for index in range(yield_count):
                calls.append(("before", index))
                yield
                calls.append(("after", index))
        finally:
            calls.append("closed")

    async def child(received):
        assert received is event
        calls.append("child")

    scheduler.stages = [SimpleNamespace(process=parent), SimpleNamespace(process=child)]
    await scheduler._process_stages(event)

    expected = []
    for index in range(yield_count):
        expected.extend([("before", index), "child", ("after", index)])
    if yield_count == 0:
        assert calls == ["closed", "child"]
    else:
        assert calls == [*expected, "closed"]


@pytest.mark.asyncio
async def test_nested_generators_unwind_in_reverse_order(scheduler, event):
    calls = []

    async def outer(_event):
        calls.append("outer before")
        yield
        calls.append("outer after")

    async def inner(_event):
        calls.append("inner before")
        yield
        calls.append("inner after")

    async def leaf(_event):
        calls.append("leaf")

    scheduler.stages = [
        SimpleNamespace(process=outer),
        SimpleNamespace(process=inner),
        SimpleNamespace(process=leaf),
    ]
    await scheduler._process_stages(event)
    assert calls == [
        "outer before",
        "inner before",
        "leaf",
        "inner after",
        "outer after",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_at", ["parent", "child"])
async def test_stop_closes_generator_without_running_remaining_stages(
    scheduler, event, stop_at
):
    calls = []

    async def parent(_event):
        try:
            calls.append("parent")
            if stop_at == "parent":
                event.stopped = True
            yield
            calls.append("unexpected parent continuation")
        finally:
            calls.append("closed")

    async def child(_event):
        calls.append("child")
        event.stopped = True

    async def leaf(_event):
        calls.append("unexpected leaf")

    scheduler.stages = [
        SimpleNamespace(process=parent),
        SimpleNamespace(process=child),
        SimpleNamespace(process=leaf),
    ]
    await scheduler._process_stages(event)
    assert calls == (
        ["parent", "closed"] if stop_at == "parent" else ["parent", "child", "closed"]
    )


@pytest.mark.asyncio
async def test_coroutine_stop_prevents_next_stage(scheduler, event):
    calls = []

    async def first(_event):
        calls.append("first")
        event.stopped = True

    async def second(_event):
        calls.append("unexpected second")

    scheduler.stages = [SimpleNamespace(process=first), SimpleNamespace(process=second)]
    await scheduler._process_stages(event)
    assert calls == ["first"]


@pytest.mark.asyncio
async def test_downstream_failure_closes_all_suspended_generators(scheduler, event):
    closed = []

    async def outer(_event):
        try:
            yield
        finally:
            closed.append("outer")

    async def inner(_event):
        try:
            yield
        finally:
            closed.append("inner")

    async def failing(_event):
        raise RuntimeError("downstream failure")

    scheduler.stages = [
        SimpleNamespace(process=outer),
        SimpleNamespace(process=inner),
        SimpleNamespace(process=failing),
    ]
    with pytest.raises(RuntimeError, match="downstream failure"):
        await scheduler._process_stages(event)
    assert closed == ["inner", "outer"]


@pytest.mark.asyncio
async def test_task_cancellation_waits_for_generator_cleanup(scheduler, event):
    entered = asyncio.Event()
    closed = []

    async def parent(_event):
        try:
            yield
        finally:
            closed.append("parent")

    async def blocked(_event):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.append("child")

    scheduler.stages = [
        SimpleNamespace(process=parent),
        SimpleNamespace(process=blocked),
    ]
    task = asyncio.create_task(scheduler._process_stages(event))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert closed == ["child", "parent"]


@pytest.mark.asyncio
async def test_empty_generator_that_stops_does_not_admit_downstream(scheduler, event):
    calls = []

    async def reject(_event):
        event.stopped = True
        for item in ():
            yield item

    async def child(_event):
        calls.append("unexpected child")

    scheduler.stages = [SimpleNamespace(process=reject), SimpleNamespace(process=child)]
    await scheduler._process_stages(event)
    assert calls == []


@pytest.mark.asyncio
async def test_real_content_safety_acceptance_reaches_downstream_once(scheduler, event):
    from astrbot.core.pipeline.content_safety_check.stage import ContentSafetyCheckStage

    safety = ContentSafetyCheckStage()
    safety.strategy_selector = SimpleNamespace(check=Mock(return_value=(True, "")))
    event.get_message_str = lambda: "accepted request"
    event.get_messages = lambda: []
    calls = []

    async def child(_event):
        calls.append("processed")

    scheduler.stages = [safety, SimpleNamespace(process=child)]
    await scheduler._process_stages(event)
    safety.strategy_selector.check.assert_called_once_with("accepted request")
    assert calls == ["processed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("addressed", [False, True])
async def test_real_content_safety_rejection_never_runs_plugins_or_model(
    scheduler, event, addressed
):
    from astrbot.core.pipeline.content_safety_check.stage import ContentSafetyCheckStage

    safety = ContentSafetyCheckStage()
    safety.strategy_selector = SimpleNamespace(
        check=Mock(return_value=(False, "blocked"))
    )
    event.is_at_or_wake_command = addressed
    event.get_message_str = lambda: "rejected request"
    event.get_messages = lambda: []
    event.result = None
    event.set_result = lambda result: setattr(event, "result", result)
    event.get_result = lambda: event.result
    event.stop_event = lambda: setattr(event, "stopped", True)
    event.send = AsyncMock()
    downstream = AsyncMock()
    scheduler.stages = [safety, SimpleNamespace(process=downstream)]

    await scheduler._process_stages(event)

    downstream.assert_not_awaited()
    assert event.is_stopped()
    assert event.send.await_count == int(addressed)
    if addressed:
        sent = event.send.await_args.args[0]
        assert "blocked" in sent.chain[0].text
