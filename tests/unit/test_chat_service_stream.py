import asyncio
import json
from unittest.mock import Mock

import pytest

from astrbot.core.chatui import view_store
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.dashboard.services.chat_service import ChatRunState, ChatService


@pytest.mark.asyncio
async def test_stream_saves_one_reply_after_its_follow_up(database, monkeypatch):
    service = object.__new__(ChatService)
    service.db = database
    service.platform_history_mgr = PlatformMessageHistoryManager(database)
    service.running_convs = {}
    service.chat_runs = {}
    service.chat_runs_by_session = {}
    reply_saved = asyncio.Event()
    frames = []
    bind_view = Mock()
    monkeypatch.setattr(view_store, "bind_message", bind_view)

    def publish(run, payload):
        frames.append(payload)
        if payload["type"] == "message_saved":
            reply_saved.set()

    service._publish_chat_run = publish
    run = ChatRunState(
        run_id="run-1",
        username="alice",
        session_id="session-1",
        turn_id="turn-1",
        platform_history_id="webchat",
        back_queue=asyncio.Queue(),
    )
    run.back_queue.put_nowait(
        {"type": "plain", "data": "Let me check.", "streaming": True}
    )
    run.back_queue.put_nowait({"type": "complete", "streaming": True})
    run.task = asyncio.create_task(service._consume_chat_run(run))
    await asyncio.wait_for(reply_saved.wait(), timeout=5)
    (first_save,) = await service.platform_history_mgr.get("webchat", run.session_id)
    follow_up = await service.platform_history_mgr.insert(
        platform_id="webchat",
        user_id=run.session_id,
        content={
            "type": "user",
            "message": [{"type": "plain", "text": "Check Shanghai."}],
        },
    )

    for event in (
        {"type": "plain", "data": "Looking up Shanghai."},
        {"type": "plain", "data": "One moment."},
        {"type": "plain", "data": "Checking the ", "streaming": True},
        {"type": "plain", "data": "latest forecast.", "streaming": True},
        {
            "type": "plain",
            "chain_type": "tool_call",
            "data": json.dumps({"id": "c1", "name": "read", "ts": 1}),
        },
        {"type": "view", "data": {"id": "forecast", "name": "forecast"}},
        {
            "type": "actionrow",
            "data": {"buttons": [], "title": "Choose an option"},
        },
        {
            "type": "plain",
            "chain_type": "tool_call_result",
            "data": json.dumps({"id": "c1", "result": "ok", "ts": 2}),
        },
        {
            "type": "plain",
            "chain_type": "tool_call",
            "data": json.dumps({"id": "c2", "name": "lookup", "ts": 3}),
        },
        {"type": "end"},
    ):
        run.back_queue.put_nowait(event)
    await asyncio.wait_for(run.task, timeout=5)
    assert frames[-2]["type"] == "message_saved"
    assert frames[-1]["type"] == "end"
    assert any(frame.get("data") == "\n\nChecking the " for frame in frames)

    # A captured input can be acknowledged after its target has already finished.
    capture_run = ChatRunState(
        run_id="follow-up",
        username=run.username,
        session_id=run.session_id,
        turn_id="follow-up-turn",
        platform_history_id=run.platform_history_id,
        back_queue=asyncio.Queue(),
        user_message_created_at=follow_up.created_at,
    )
    capture_run.back_queue.put_nowait(
        {
            "type": "follow_up_captured",
            "data": {"target_run_id": run.run_id, "_target_turn_id": run.turn_id},
        }
    )
    capture_run.back_queue.put_nowait({"type": "end"})
    await asyncio.wait_for(service._consume_chat_run(capture_run), timeout=5)

    (user_record, record) = await service.platform_history_mgr.get(
        "webchat", run.session_id
    )
    assert user_record.id == follow_up.id
    assert record.id == first_save.id
    bind_view.assert_called_once_with("forecast", str(record.id))
    parts = record.content["message"]
    assert [part["type"] for part in parts] == [
        "plain",
        "tool_call",
        "view",
        "actionrow",
        "tool_call",
    ]
    assert parts[0]["text"] == (
        "Let me check.\n\nLooking up Shanghai.\n\nOne moment.\n\nChecking the latest forecast."
    )
    (finished,) = parts[1]["tool_calls"]
    (interrupted,) = parts[4]["tool_calls"]
    assert finished["id"] == "c1"
    assert finished["result"] == "ok"
    assert finished["finished_ts"] == 2
    assert interrupted["id"] == "c2"
    assert interrupted["phase"] == "unknown"
