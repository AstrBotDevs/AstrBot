"""Regression tests for releasing session locks after response failures."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.pipeline.process_stage.method.agent_request import (
    AgentRequestSubStage,
)
from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.session_llm_manager import SessionServiceManager
from astrbot.core.utils.session_lock import SessionLockManager


@pytest.mark.asyncio
@pytest.mark.parametrize("plugin_request", [False, True])
@pytest.mark.parametrize("outcome", ["failure", "cancel"])
async def test_downstream_exit_releases_upstream_session_lock(
    monkeypatch, plugin_request, outcome
):
    """Close every forwarding generator before another request acquires the lock.

    Args:
        monkeypatch: Isolate the session service check.
        plugin_request: Whether a plugin supplies the agent request.
        outcome: Downstream exception or cancellation to propagate.
    """
    locks = SessionLockManager()
    session_id = "telegram:FriendMessage:test"
    closed = []
    retained_generators = []

    async def agent_process(event, prefix):
        async with locks.acquire_lock(session_id):
            try:
                yield
            finally:
                closed.append("agent")

    def retain_agent(event, prefix):
        # Retain the generator, as an exception traceback can do in production.
        generator = agent_process(event, prefix)
        retained_generators.append(generator)
        return generator

    async def plugin_process(event):
        try:
            yield ProviderRequest()
        finally:
            closed.append("plugin")

    async def respond(event):
        assert session_id in locks._get_loop_manager()._locks
        if outcome == "failure":
            raise TimeoutError("Telegram send timed out")
        if outcome == "cancel":
            raise asyncio.CancelledError

    config = {"provider_settings": {"enable": True}}
    ctx = SimpleNamespace(astrbot_config=config)
    agent = AgentRequestSubStage()
    agent.ctx = ctx
    agent.config = config
    agent.prov_wake_prefix = ""
    agent.agent_sub_stage = SimpleNamespace(process=retain_agent)
    monkeypatch.setattr(
        SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )
    process = ProcessStage()
    process.ctx = ctx
    process.agent_sub_stage = agent
    process.star_request_sub_stage = SimpleNamespace(process=plugin_process)
    scheduler = PipelineScheduler.__new__(PipelineScheduler)
    scheduler.stages = [process, SimpleNamespace(process=respond)]
    event = MagicMock()
    event.get_extra.return_value = ["plugin"] if plugin_request else []
    event._has_send_oper = False
    event.is_at_or_wake_command = True
    event.call_llm = False
    event.get_result.return_value = None
    event.is_stopped.return_value = False

    expected = TimeoutError if outcome == "failure" else asyncio.CancelledError
    with pytest.raises(expected):
        await scheduler._process_stages(event)

    assert closed == (["agent", "plugin"] if plugin_request else ["agent"])
    assert session_id not in locks._get_loop_manager()._locks
    async with locks.acquire_lock(session_id):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("plugin_request", [False, True])
@pytest.mark.parametrize("reply_count", [0, 1, 3])
async def test_normal_replies_finish_before_generator_cleanup(
    monkeypatch, plugin_request, reply_count
):
    """Preserve multiple yields and post-reply work on successful requests.

    Args:
        monkeypatch: Isolate session service checks.
        plugin_request: Whether a plugin supplies the provider request.
        reply_count: Number of results yielded by the agent.
    """
    actions = []
    config = {"provider_settings": {"enable": True}}
    ctx = SimpleNamespace(astrbot_config=config)
    event = MagicMock()
    event.get_extra.return_value = ["plugin"] if plugin_request else []
    event.get_result.return_value = None
    event.is_stopped.return_value = False
    event.is_at_or_wake_command = True
    event.call_llm = False
    event._has_send_oper = False

    async def agent_process(current, prefix):
        try:
            for index in range(reply_count):
                actions.append(("produce", index))
                yield
                actions.append(("resume", index))
            actions.append("history")
        finally:
            actions.append("agent_cleanup")

    async def plugin_process(current):
        try:
            actions.append("plugin_start")
            yield ProviderRequest()
            actions.append("plugin_resume")
        finally:
            actions.append("plugin_cleanup")

    monkeypatch.setattr(
        SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )
    agent = AgentRequestSubStage()
    agent.ctx = ctx
    agent.config = config
    agent.prov_wake_prefix = ""
    agent.agent_sub_stage = SimpleNamespace(process=agent_process)
    process = ProcessStage()
    process.ctx = ctx
    process.agent_sub_stage = agent
    process.star_request_sub_stage = SimpleNamespace(process=plugin_process)

    async for _ in process.process(event):
        actions.append("deliver")
        event._has_send_oper = True

    expected = ["plugin_start"] if plugin_request else []
    for index in range(reply_count):
        expected.extend([("produce", index), "deliver", ("resume", index)])
    expected.extend(["history", "agent_cleanup"])
    if plugin_request:
        if reply_count == 0:
            expected.append("deliver")
        expected.extend(["plugin_resume", "plugin_cleanup"])
    assert actions == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_mode", ["stop", "cancel"])
async def test_scheduler_closes_in_owning_task(exit_mode):
    """Finalize suspended stages in their owning task and context.

    Args:
        exit_mode: Stop propagation or cancel the actual pipeline task.
    """
    from contextvars import ContextVar

    scope = ContextVar("pipeline_cleanup_scope", default=None)
    entered = asyncio.Event()
    cleanup = []
    event = MagicMock()
    event.is_stopped.return_value = False

    async def upstream(current):
        owner = asyncio.current_task()
        token = scope.set("stage")
        try:
            if exit_mode == "stop":
                current.is_stopped.return_value = True
            yield
            cleanup.append("resumed")
        finally:
            cleanup.append((asyncio.current_task() is owner, scope.get()))
            scope.reset(token)

    async def downstream(current):
        entered.set()
        await asyncio.Event().wait()

    scheduler = PipelineScheduler.__new__(PipelineScheduler)
    scheduler.stages = [SimpleNamespace(process=upstream)]
    if exit_mode == "cancel":
        scheduler.stages.append(SimpleNamespace(process=downstream))
    task = asyncio.create_task(scheduler._process_stages(event))
    if exit_mode == "cancel":
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await task
    assert cleanup == [(True, "stage")]
    assert scope.get() is None
