import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


def test_history_recomputes_approval_remaining_time():
    """A reloaded approval card gets the time left, not a stale value."""
    from astrbot.dashboard.services import chat_service

    row = {
        "type": "actionrow",
        "expires_at": datetime.now(timezone.utc).timestamp() + 30,
        "expires_in": 999,
    }
    record = SimpleNamespace(
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        model_dump=lambda: {"content": {"message": [dict(row)]}},
    )
    served = chat_service.serialize_history_entry(record)["content"]["message"][0]
    normalized = chat_service.normalize_reasoning_message_parts([dict(row)])[0]
    # The snapshot sent to a client that reconnects to a running turn.
    snapshot = chat_service.build_bot_history_content([dict(row)])["message"][0]
    assert 0 < served["expires_in"] <= 30
    assert 0 < normalized["expires_in"] <= 30
    assert 0 < snapshot["expires_in"] <= 30
    expired = chat_service.normalize_reasoning_message_parts(
        [{**row, "expires_at": 1.0}]
    )[0]
    assert expired["expires_in"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("has_result", [False, True])
async def test_sse_turn_is_one_history_record(has_result):
    """One turn is one record; a card keeps its place after the tool call."""
    import json

    from astrbot.dashboard.services.chat_service import ChatRunState, ChatService

    records: dict[int, list[dict]] = {}

    async def insert(**kwargs):
        records[len(records) + 1] = kwargs["content"]["message"]
        return SimpleNamespace(id=len(records), created_at=datetime.now(timezone.utc))

    async def update(message_id, content=None, turn_id=None):
        records[message_id] = content["message"]

    service = object.__new__(ChatService)
    service.platform_history_mgr = SimpleNamespace(insert=insert, update=update)
    service.running_convs = {}
    service.chat_runs = {}
    service.chat_runs_by_session = {}
    service._publish_chat_run = lambda run, payload: None
    run = ChatRunState(
        run_id="run-1",
        username="alice",
        session_id="s1",
        turn_id="t1",
        platform_history_id="webchat",
        back_queue=asyncio.Queue(),
    )
    for item in (
        {"type": "plain", "data": "Let me check.", "streaming": True},
        {"type": "complete", "data": "Let me check.", "streaming": True},
        {
            "type": "plain",
            "chain_type": "tool_call",
            "data": json.dumps({"id": "c1", "name": "write", "ts": 1.0}),
        },
        {"type": "actionrow", "data": {"buttons": [], "title": "approve?"}},
        {
            "type": "plain",
            "chain_type": "tool_call_result",
            "data": json.dumps({"id": "c1", "result": "ok", "ts": 2.0}),
        },
        {"type": "plain", "data": "Done.", "streaming": True},
        {"type": "complete", "data": "Done.", "streaming": True},
        {"type": "end", "data": ""},
    ):
        if not has_result and item.get("chain_type") == "tool_call_result":
            continue
        await run.back_queue.put(item)

    await asyncio.wait_for(service._consume_chat_run(run), timeout=2)

    assert list(records) == [1]
    calls = [
        call
        for part in records[1]
        if part["type"] == "tool_call"
        for call in part["tool_calls"]
    ]
    assert len(calls) == 1
    assert [part["type"] for part in records[1]] == [
        "plain",
        "tool_call",
        "actionrow",
        "plain",
    ]
    if not has_result:
        assert calls[0]["phase"] == "unknown"
        assert "finished_ts" not in calls[0]
        return
    assert calls[0]["result"] == "ok"
    assert calls[0]["finished_ts"] == 2.0


def test_accumulator_keeps_call_position_and_marks_unfinished_calls_at_end():
    import json

    from astrbot.dashboard.services.chat_service import BotMessageAccumulator

    acc = BotMessageAccumulator()
    for chain_type, data in (
        ("tool_call", {"id": "a", "name": "read", "ts": 1}),
        ("tool_call", {"id": "b", "name": "shell", "ts": 2}),
        ("tool_call_result", {"id": "a", "result": "ok", "ts": 3}),
        ("tool_call_result", {"id": "orphan", "result": "late", "ts": 4}),
    ):
        acc.add_plain(json.dumps(data), chain_type=chain_type, streaming=False)
    acc.add_part({"type": "actionrow", "title": "approve?"})

    # Mid-turn: running calls keep their place and are not marked yet.
    parts = acc.build_message_parts()
    assert [p.get("tool_calls", [{}])[0].get("id") for p in parts] == [
        "a",
        "b",
        "orphan",
        None,
    ]
    assert "phase" not in parts[1]["tool_calls"][0]

    parts = acc.build_message_parts(final=True)
    assert parts[0]["tool_calls"][0]["finished_ts"] == 3
    assert parts[1]["tool_calls"][0]["phase"] == "unknown"
    assert "phase" not in parts[0]["tool_calls"][0]
    assert acc.pending_tool_calls == {}


@pytest.mark.asyncio
async def test_failed_run_keeps_the_turn_record_and_marks_open_calls():
    """An unexpected run failure still saves one record with the error card."""
    import json

    from astrbot.dashboard.services.chat_service import ChatRunState, ChatService

    records: dict[int, list[dict]] = {}

    async def insert(**kwargs):
        records[len(records) + 1] = kwargs["content"]["message"]
        return SimpleNamespace(id=len(records), created_at=datetime.now(timezone.utc))

    async def update(message_id, content=None, turn_id=None):
        records[message_id] = content["message"]

    class FailingQueue:
        def __init__(self):
            self.items = [
                {
                    "type": "plain",
                    "chain_type": "tool_call",
                    "data": json.dumps({"id": "c1", "name": "shell", "ts": 1.0}),
                }
            ]

        async def get(self):
            if self.items:
                return self.items.pop(0)
            raise RuntimeError("queue broke")

    service = object.__new__(ChatService)
    service.platform_history_mgr = SimpleNamespace(insert=insert, update=update)
    service.running_convs = {}
    service.chat_runs = {}
    service.chat_runs_by_session = {}
    service._publish_chat_run = lambda run, payload: None
    run = ChatRunState(
        run_id="run-1",
        username="alice",
        session_id="s1",
        turn_id="t1",
        platform_history_id="webchat",
        back_queue=FailingQueue(),
    )

    await asyncio.wait_for(service._consume_chat_run(run), timeout=2)

    assert run.status == "failed"
    assert list(records) == [1]
    assert [part["type"] for part in records[1]] == ["tool_call", "error"]
    assert records[1][0]["tool_calls"][0]["phase"] == "unknown"
    assert [part["type"] for part in run.message_parts] == ["tool_call", "error"]
