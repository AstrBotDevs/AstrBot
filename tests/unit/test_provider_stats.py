from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai.types.chat.chat_completion import ChatCompletion
from sqlalchemy import event
from sqlmodel import select

from astrbot.core.db import chat_usage_writer
from astrbot.core.db.po import ChatRequestStat
from astrbot.core.pipeline.process_stage.method import star_request
from astrbot.core.provider.sources import chat_request, request_retry
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType
from astrbot.dashboard.services.stat_service import StatService


@pytest.mark.asyncio
async def test_direct_plugin_chat_counts_each_attempt_and_keeps_historical_tokens(
    temp_db,
    monkeypatch,
):
    monkeypatch.setattr(chat_request, "db_helper", temp_db)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    with pytest.warns(DeprecationWarning, match="insert_provider_stat"):
        await temp_db.insert_provider_stat(
            umo="test:FriendMessage:old",
            provider_id="old-provider",
            stats={"token_usage": {"input_other": 9}},
        )
    provider = ProviderOpenAIOfficial(
        {"id": "test-provider", "key": ["test-key"], "model": "default-model"},
        {},
    )
    completion = ChatCompletion.model_validate(
        {
            "id": "completion",
            "object": "chat.completion",
            "created": 0,
            "model": "other-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                },
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
                "prompt_tokens_details": {"cached_tokens": 3},
            },
        }
    )
    monkeypatch.setattr(
        provider.client.chat.completions,
        "create",
        AsyncMock(side_effect=[httpx.ConnectError("retry"), completion]),
    )

    async def handle(event):
        response = await provider.text_chat(
            prompt="hello", model="other-model", request_max_retries=2
        )
        assert response.completion_text == "ok"

    plugin = StarMetadata(name="test_plugin", author="author")
    monkeypatch.setitem(star_request.star_map, "test_plugin", plugin)
    handler = SimpleNamespace(
        handler=handle,
        handler_name="handle",
        handler_full_name="test_plugin.handle",
        handler_module_path="test_plugin",
        event_type=EventType.AdapterMessageEvent,
        event_filters=[],
        extras_configs={},
    )
    event = MagicMock()
    event.get_extra.side_effect = {"activated_handlers": [handler]}.get
    event.is_stopped.return_value = False
    try:
        async for _ in star_request.StarRequestSubStage().process(event):
            pass
    finally:
        await provider.terminate()

    await temp_db.chat_usage_writer.flush()
    async with temp_db.get_db() as session:
        rows = (
            (
                await session.execute(
                    select(ChatRequestStat).order_by(ChatRequestStat.id)
                )
            )
            .scalars()
            .all()
        )
    assert [(row.status, row.token_output) for row in rows] == [
        ("error", None),
        ("completed", 7),
    ]
    assert {row.plugin_id for row in rows} == {plugin.plugin_id}
    assert {row.provider_model for row in rows} == {"other-model"}
    assert rows[1].token_input_other == 8
    assert rows[1].token_input_cached == 3

    service = StatService(temp_db, MagicMock(), {})
    stats = await service.get_provider_token_stats(1)
    assert stats["range_total_tokens"] == 27
    assert stats["range_total_calls"] == 2
    assert stats["range_unknown_usage_calls"] == 1
    assert stats["range_by_plugin"] == [
        {"plugin_id": plugin.plugin_id, "tokens": 18, "calls": 2},
    ]


@pytest.mark.asyncio
async def test_usage_queue_batches_writes_and_drains_on_close(temp_db, monkeypatch):
    monkeypatch.setattr(chat_usage_writer, "QUEUE_CAPACITY", 3)
    monkeypatch.setattr(chat_usage_writer, "BATCH_SIZE", 2)
    writer = chat_usage_writer.ChatUsageWriter(temp_db)
    await temp_db.initialize()
    batch_sizes = []

    @event.listens_for(temp_db.engine.sync_engine, "before_cursor_execute")
    def count_inserts(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO chat_request_stats"):
            batch_sizes.append(len(parameters) if executemany else 1)

    for output in range(4):
        writer.enqueue(
            ChatRequestStat(
                created_at=datetime.now(timezone.utc),
                provider_id="provider",
                provider_model="model",
                status="completed",
                token_output=output,
                duration=0.1,
            )
        )
    assert batch_sizes == []

    await writer.close()

    assert batch_sizes == [2, 1]
    async with temp_db.get_db() as session:
        result = await session.execute(
            select(ChatRequestStat.token_output).order_by(ChatRequestStat.id)
        )
        assert result.scalars().all() == [0, 1, 2]
