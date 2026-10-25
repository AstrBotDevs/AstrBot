"""Regression coverage for proactive delivery and concurrent conversation history."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.astr_main_agent import _get_session_conv
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.cron.manager import CronJobManager
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.tools.message_tools import SendMessageToUserTool
from astrbot.core.utils.history_saver import (
    PROACTIVE_CONVERSATION_ID_KEY,
    PROACTIVE_SAVED_TEXTS_KEY,
    persist_agent_history,
)
from astrbot.core.utils.session_lock import session_lock_manager


@pytest_asyncio.fixture
async def proactive_session(temp_db):
    """Create an isolated conversation backed by SQLite.

    Args:
        temp_db: Temporary database fixture.

    Returns:
        Context, event, tool and conversation data for a proactive run.
    """
    await temp_db.initialize()
    umo = "test:FriendMessage:user123"
    initial = [{"role": "user", "content": "Old question"}]
    row = await temp_db.create_conversation(
        user_id=umo, platform_id="test", content=initial
    )
    manager = ConversationManager(temp_db)
    manager.session_conversations[umo] = row.conversation_id
    tool = SendMessageToUserTool()
    ctx = SimpleNamespace(
        conversation_manager=manager,
        get_config=lambda **kwargs: {"admins_id": [], "provider_settings": {}},
        get_llm_tool_manager=lambda: SimpleNamespace(get_builtin_tool=lambda cls: tool),
        send_message=AsyncMock(return_value=True),
    )
    event = CronMessageEvent(
        context=ctx, session=MessageSession.from_str(umo), message="Already taken"
    )
    return SimpleNamespace(
        db=temp_db,
        manager=manager,
        ctx=ctx,
        event=event,
        run_context=ContextWrapper(context=SimpleNamespace(event=event, context=ctx)),
        tool=tool,
        umo=umo,
        cid=row.conversation_id,
        initial=initial,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["cron", "background"])
@pytest.mark.parametrize("finish_during_reply", [False, True])
async def test_delivered_message_is_visible_before_job_finishes(
    proactive_session, monkeypatch, entrypoint, finish_during_reply
):
    """Preserve a quick reply regardless of which run finishes first.

    Args:
        proactive_session: Isolated conversation fixture.
        monkeypatch: Pytest patch fixture.
        entrypoint: Proactive agent entrypoint to exercise.
        finish_during_reply: Whether the job finishes while the user owns the lock.
    """
    s = proactive_session
    reminder = "Time to take your medicine"
    sent = asyncio.Event()
    finish = asyncio.Event()
    finishing = asyncio.Event()
    captured = {}

    class PausedRunner:
        state = AgentState.DONE

        async def step_until_done(self, max_steps):
            """Deliver a real tool message and pause the simulated model loop.

            Args:
                max_steps: Runner step limit.

            Yields:
                No intermediate runner responses.
            """
            result = await s.tool.call(
                ContextWrapper(
                    context=SimpleNamespace(event=captured["event"], context=s.ctx)
                ),
                messages=[{"type": "plain", "text": reminder}],
            )
            assert result.startswith("Message sent")
            sent.set()
            await finish.wait()
            finishing.set()
            if False:
                yield None

        def get_final_llm_resp(self):
            """Return the same text as the delivery to exercise deduplication.

            Returns:
                Final assistant response.
            """
            return LLMResponse(role="assistant", completion_text=reminder)

    async def build(**kwargs):
        """Replace model construction while retaining the actual wakeup code.

        Args:
            **kwargs: Main agent construction arguments.

        Returns:
            Controllable runner.
        """
        captured.update(kwargs)
        return SimpleNamespace(agent_runner=PausedRunner())

    monkeypatch.setattr("astrbot.core.astr_main_agent.build_main_agent", build)
    if entrypoint == "cron":
        manager = CronJobManager(s.db)
        manager.ctx = s.ctx
        coro = manager._woke_main_agent(
            message="Run reminder",
            session_str=s.umo,
            delivery_session_str=s.umo,
            extras={"cron_job": {"id": "job", "name": "Reminder"}},
        )
    else:
        coro = FunctionToolExecutor._wake_main_agent_for_background_result(
            s.run_context,
            task_id="task",
            tool_name="test_tool",
            result_text="Ready",
            tool_args={},
            note="Notify user",
            summary_name="Test task",
        )
    job = asyncio.create_task(coro)
    try:
        await asyncio.wait_for(sent.wait(), 5)
        assert not job.done()
        s.ctx.send_message.assert_awaited_once()
        async with session_lock_manager.acquire_lock(s.umo):
            conv = await _get_session_conv(s.event, s.ctx)
            req = ProviderRequest(
                prompt="Already taken",
                conversation=conv,
                contexts=json.loads(conv.history),
            )
            assert {"role": "assistant", "content": reminder} in req.contexts
            if finish_during_reply:
                finish.set()
                await asyncio.wait_for(finishing.wait(), 5)
                assert not job.done()
            history = req.contexts + [
                {"role": "user", "content": "Already taken"},
                {"role": "assistant", "content": "Understood"},
            ]
            stage = InternalAgentSubStage()
            stage.conv_manager = s.manager
            await stage._save_to_history(
                s.event,
                req,
                LLMResponse(role="assistant", completion_text="Understood"),
                [Message(**item) for item in history],
                None,
            )
        finish.set()
        await asyncio.wait_for(job, 5)
        final = await s.manager.get_conversation(s.umo, s.cid)
        assert "Already taken" in final.history
        assert "Understood" in final.history
        assert final.history.count(reminder) == 1
        assert (
            "[CronJob]" if entrypoint == "cron" else "[BackgroundTask]"
        ) in final.history
    finally:
        finish.set()
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


@pytest.mark.asyncio
async def test_task_summary_preserves_history_written_after_start(proactive_session):
    """Append the summary to current history, not the task's stale snapshot.

    Args:
        proactive_session: Isolated conversation fixture.
    """
    s = proactive_session
    old = await s.manager.get_conversation(s.umo, s.cid)
    updated = s.initial + [{"role": "user", "content": "A newer message"}]
    await s.manager.update_conversation(s.umo, s.cid, history=updated)
    await persist_agent_history(
        s.manager,
        event=s.event,
        req=ProviderRequest(conversation=old),
        summary_note="[CronJob] finished",
    )
    final = await s.manager.get_conversation(s.umo, s.cid)
    assert json.loads(final.history)[: len(updated)] == updated


@pytest.mark.asyncio
async def test_reply_waits_for_delivery_to_be_persisted(proactive_session):
    """Close the gap between platform delivery and the database write.

    Args:
        proactive_session: Isolated conversation fixture.
    """
    s = proactive_session
    s.event.set_extra(PROACTIVE_CONVERSATION_ID_KEY, s.cid)
    platform_delivered = asyncio.Event()
    return_from_send = asyncio.Event()
    reader_started = asyncio.Event()
    reader_acquired = asyncio.Event()

    async def send(*args):
        """Pause after platform delivery but before returning to the tool.

        Args:
            *args: Platform destination and message chain.

        Returns:
            Successful platform delivery.
        """
        platform_delivered.set()
        await return_from_send.wait()
        return True

    async def read_reply_context():
        """Read persisted history using the ordinary reply's session lock.

        Returns:
            Conversation snapshot visible to the reply.
        """
        reader_started.set()
        async with session_lock_manager.acquire_lock(s.umo):
            reader_acquired.set()
            return await s.manager.get_conversation(s.umo, s.cid)

    s.ctx.send_message.side_effect = send
    delivery = asyncio.create_task(
        s.tool.call(
            s.run_context,
            messages=[{"type": "plain", "text": "Reminder"}],
        )
    )
    reader = None
    try:
        await asyncio.wait_for(platform_delivered.wait(), 5)
        reader = asyncio.create_task(read_reply_context())
        await asyncio.wait_for(reader_started.wait(), 5)
        assert not reader_acquired.is_set()
        return_from_send.set()
        assert (await asyncio.wait_for(delivery, 5)).startswith("Message sent")
        conv = await asyncio.wait_for(reader, 5)
        assert "Reminder" in conv.history
    finally:
        return_from_send.set()
        tasks = [task for task in (delivery, reader) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_original", [False, True])
async def test_proactive_history_stays_bound_to_original_conversation(
    proactive_session, delete_original
):
    """Switching or deleting conversations must not redirect task history.

    Args:
        proactive_session: Isolated conversation fixture.
        delete_original: Whether the original conversation is also deleted.
    """
    s = proactive_session
    original = await s.manager.get_conversation(s.umo, s.cid)
    s.event.set_extra(PROACTIVE_CONVERSATION_ID_KEY, s.cid)
    selected = await s.db.create_conversation(
        user_id=s.umo, platform_id="test", content=[]
    )
    s.manager.session_conversations[s.umo] = selected.conversation_id
    if delete_original:
        await s.db.delete_conversation(s.cid)
    result = await s.tool.call(
        s.run_context,
        messages=[{"type": "plain", "text": "Reminder"}],
    )
    assert result.startswith("Message sent")
    await persist_agent_history(
        s.manager,
        event=s.event,
        req=ProviderRequest(conversation=original),
        summary_note="[CronJob] finished",
    )
    current = await s.manager.get_conversation(s.umo, selected.conversation_id)
    assert json.loads(current.history) == []
    original = await s.manager.get_conversation(s.umo, s.cid)
    if delete_original:
        assert original is None
    else:
        assert "Reminder" in original.history
        assert "[CronJob] finished" in original.history


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["normal", "media"])
async def test_normal_and_media_deliveries_skip_proactive_history(
    proactive_session, case
):
    """Leave normal history to the pipeline and skip textless deliveries.

    Args:
        proactive_session: Isolated conversation fixture.
        case: Delivery condition that should not add proactive text history.
    """
    s = proactive_session
    if case == "media":
        s.event.set_extra(PROACTIVE_CONVERSATION_ID_KEY, s.cid)
    messages = (
        [{"type": "image", "url": "https://example.invalid/image.png"}]
        if case == "media"
        else [{"type": "plain", "text": "Reminder"}]
    )
    coro = s.tool.call(s.run_context, messages=messages)
    if case == "normal":
        # Normal pipeline calls already hold the lock; acquiring it again deadlocks.
        async with session_lock_manager.acquire_lock(s.umo):
            result = await asyncio.wait_for(coro, 5)
    else:
        result = await asyncio.wait_for(coro, 5)
    assert result.startswith("Message sent")
    final = await s.manager.get_conversation(s.umo, s.cid)
    assert json.loads(final.history) == s.initial
    assert not s.event.get_extra(PROACTIVE_SAVED_TEXTS_KEY)


@pytest.mark.asyncio
async def test_storage_failure_does_not_turn_successful_send_into_retry(
    proactive_session, monkeypatch
):
    """Keep send success distinct from persistence failure.

    Args:
        proactive_session: Isolated conversation fixture.
        monkeypatch: Pytest patch fixture.
    """
    s = proactive_session
    s.event.set_extra(PROACTIVE_CONVERSATION_ID_KEY, s.cid)
    monkeypatch.setattr(
        s.manager,
        "update_conversation",
        AsyncMock(side_effect=RuntimeError("DB unavailable")),
    )
    result = await s.tool.call(
        s.run_context,
        messages=[{"type": "plain", "text": "Reminder"}],
    )
    assert result.startswith("Message sent")
    s.ctx.send_message.assert_awaited_once()
    assert not s.event.get_extra(PROACTIVE_SAVED_TEXTS_KEY)


@pytest.mark.asyncio
async def test_cancel_after_delivery_finishes_history_write_before_unlocking(
    proactive_session, monkeypatch
):
    """Keep a delivered reminder visible even if its tool execution is cancelled.

    Args:
        proactive_session: Isolated conversation fixture.
        monkeypatch: Pytest patch fixture.
    """
    s = proactive_session
    s.event.set_extra(PROACTIVE_CONVERSATION_ID_KEY, s.cid)
    writing = asyncio.Event()
    allow_write = asyncio.Event()
    update = s.manager.update_conversation

    async def paused_write(*args, **kwargs):
        """Pause the database write after platform delivery has succeeded.

        Args:
            *args: Conversation identifiers.
            **kwargs: History update arguments.
        """
        writing.set()
        await allow_write.wait()
        await update(*args, **kwargs)

    monkeypatch.setattr(s.manager, "update_conversation", paused_write)
    delivery = asyncio.create_task(
        s.tool.call(
            s.run_context,
            messages=[{"type": "plain", "text": "Reminder"}],
        )
    )
    try:
        await asyncio.wait_for(writing.wait(), 5)
        s.ctx.send_message.assert_awaited_once()
        for _ in range(2):
            delivery.cancel()
            await asyncio.sleep(0)
            assert not delivery.done()
        allow_write.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(delivery, 5)
        async with session_lock_manager.acquire_lock(s.umo):
            final = await s.manager.get_conversation(s.umo, s.cid)
        assert final.history.count("Reminder") == 1
        assert s.event.get_extra(PROACTIVE_SAVED_TEXTS_KEY) == ["Reminder"]
    finally:
        allow_write.set()
        if not delivery.done():
            delivery.cancel()
        await asyncio.gather(delivery, return_exceptions=True)
