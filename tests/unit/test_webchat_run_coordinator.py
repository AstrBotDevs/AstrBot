import asyncio

import pytest

from astrbot.core.webchat.queue_manager import WebChatQueueManager
from astrbot.core.webchat.run_coordinator import (
    DuplicateWebChatRunError,
    WebChatRunCoordinator,
)


@pytest.mark.asyncio
async def test_dispatch_creates_response_queue_before_request_input() -> None:
    queue_manager = WebChatQueueManager()
    coordinator = WebChatRunCoordinator(queue_manager)
    run = coordinator.create_run(
        session_id="session-1",
        username="alice",
        request_id="request-1",
    )

    await coordinator.dispatch(run, {"message": [{"type": "plain", "text": "hi"}]})

    assert queue_manager.back_queues["request-1"] is run.back_queue
    assert await queue_manager.queues["session-1"].get() == (
        "alice",
        "session-1",
        {
            "message": [{"type": "plain", "text": "hi"}],
            "message_id": "request-1",
        },
    )


def test_duplicate_request_id_is_rejected_without_cross_session_state() -> None:
    coordinator = WebChatRunCoordinator(WebChatQueueManager())
    coordinator.create_run(
        session_id="session-1",
        username="alice",
        request_id="request-1",
    )

    with pytest.raises(DuplicateWebChatRunError):
        coordinator.create_run(
            session_id="session-2",
            username="bob",
            request_id="request-1",
        )

    assert [run.request_id for run in coordinator.get_session_runs("session-1")] == [
        "request-1"
    ]
    assert coordinator.get_session_runs("session-2") == []


@pytest.mark.asyncio
async def test_result_observation_preserves_request_scoped_protocol_state() -> None:
    coordinator = WebChatRunCoordinator(WebChatQueueManager())
    run = coordinator.create_run(
        session_id="session-1",
        username="alice",
        request_id="request-1",
    )
    await run.back_queue.put(
        {
            "type": "run_started",
            "data": {"run_id": "request-1"},
            "message_id": "request-1",
        }
    )
    await run.back_queue.put(
        {
            "type": "agent_stats",
            "chain_type": "agent_stats",
            "data": '{"call": 1}',
            "message_id": "request-1",
        }
    )
    await run.back_queue.put(
        {
            "type": "follow_up_captured",
            "data": {"text": "next"},
            "message_id": "request-1",
        }
    )
    await run.back_queue.put({"type": "end", "data": "", "message_id": "request-1"})

    assert (await coordinator.next_result(run))["type"] == "run_started"
    assert (await coordinator.next_result(run))["type"] == "agent_stats"
    assert (await coordinator.next_result(run))["type"] == "follow_up_captured"
    assert (await coordinator.next_result(run))["type"] == "end"
    assert run.started is True
    assert run.agent_stats == [{"call": 1}]
    assert run.follow_up_capture == {"text": "next"}
    assert run.completion_seen is True
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_same_session_runs_keep_distinct_message_ids_when_one_finishes() -> None:
    coordinator = WebChatRunCoordinator(WebChatQueueManager())
    first = coordinator.create_run(
        session_id="session-1",
        username="alice",
        request_id="request-1",
    )
    second = coordinator.create_run(
        session_id="session-1",
        username="alice",
        request_id="request-2",
    )
    await first.back_queue.put({"type": "end", "message_id": "request-1"})
    await second.back_queue.put(
        {
            "type": "agent_stats",
            "chain_type": "agent_stats",
            "data": '{"call": 2}',
            "message_id": "request-2",
        }
    )

    assert (await coordinator.next_result(first))["message_id"] == "request-1"
    await coordinator.close_run(first)
    assert [run.request_id for run in coordinator.get_session_runs("session-1")] == [
        "request-2"
    ]
    assert (await coordinator.next_result(second))["message_id"] == "request-2"
    assert second.agent_stats == [{"call": 2}]


@pytest.mark.asyncio
async def test_close_session_cancels_only_its_own_request_tasks() -> None:
    coordinator = WebChatRunCoordinator(WebChatQueueManager())
    first = coordinator.create_run(
        session_id="session-1",
        username="alice",
        request_id="request-1",
    )
    second = coordinator.create_run(
        session_id="session-2",
        username="alice",
        request_id="request-2",
    )
    first_task = coordinator.start_task(
        first,
        asyncio.Event().wait(),
        name="request-1",
    )
    second_task = coordinator.start_task(
        second,
        asyncio.Event().wait(),
        name="request-2",
    )

    await coordinator.close_session("session-1", remove_input_queue=True)

    assert first_task.cancelled()
    assert coordinator.get_run("request-1") is None
    assert coordinator.get_run("request-2") is second
    assert "session-1" not in coordinator.queue_manager.queues
    assert not second_task.done()

    second_task.cancel()
    await asyncio.gather(second_task, return_exceptions=True)
