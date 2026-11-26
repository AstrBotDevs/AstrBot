import asyncio
import json

import pytest

from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.dashboard.services.chat_service import ChatRunState, ChatService


@pytest.mark.asyncio
async def test_stream_saves_one_record_with_ordered_tool_calls(database):
    service = object.__new__(ChatService)
    service.platform_history_mgr = PlatformMessageHistoryManager(database)
    service.running_convs = {}
    service.chat_runs = {}
    service.chat_runs_by_session = {}
    run = ChatRunState(
        run_id="run-1",
        username="alice",
        session_id="session-1",
        turn_id="turn-1",
        platform_history_id="webchat",
        back_queue=asyncio.Queue(),
    )
    for event in (
        {"type": "plain", "data": "Let me check.", "streaming": True},
        {"type": "complete", "streaming": True},
        {
            "type": "plain",
            "chain_type": "tool_call",
            "data": json.dumps({"id": "c1", "name": "read", "ts": 1}),
        },
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
    await asyncio.wait_for(service._consume_chat_run(run), timeout=5)

    (record,) = await service.platform_history_mgr.get("webchat", run.session_id)
    parts = record.content["message"]
    assert [part["type"] for part in parts] == [
        "plain",
        "tool_call",
        "actionrow",
        "tool_call",
    ]
    (finished,) = parts[1]["tool_calls"]
    (interrupted,) = parts[3]["tool_calls"]
    assert finished["id"] == "c1"
    assert finished["result"] == "ok"
    assert finished["finished_ts"] == 2
    assert interrupted["id"] == "c2"
    assert interrupted["phase"] == "unknown"
