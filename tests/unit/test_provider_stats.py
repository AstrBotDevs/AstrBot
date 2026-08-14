import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from astrbot.core.agent.response import AgentStats
from astrbot.core.db.po import ProviderStat
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.provider.entities import ProviderRequest, TokenUsage
from astrbot.core.provider.stats import ProviderStatSegment


@pytest.mark.asyncio
async def test_record_internal_agent_stats_persists_provider_stat(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(internal, "db_helper", temp_db)

    event = SimpleNamespace(unified_msg_origin="webchat:FriendMessage:session-42")
    req = ProviderRequest(
        conversation=SimpleNamespace(cid="conv-123"),
    )
    stats = AgentStats(
        token_usage=TokenUsage(input_other=11, input_cached=3, output=7),
        start_time=100.0,
        end_time=108.5,
        time_to_first_token=0.6,
    )
    provider = SimpleNamespace(
        provider_config={"id": "provider-1"},
        meta=lambda: SimpleNamespace(id="provider-1", type="openai"),
        get_model=lambda: "gpt-4.1",
    )
    agent_runner = SimpleNamespace(
        provider=provider,
        stats=stats,
        was_aborted=lambda: False,
    )
    final_resp = SimpleNamespace(role="assistant")

    await internal._record_internal_agent_stats(
        event,
        req,
        agent_runner,
        final_resp,
    )

    async with temp_db.get_db() as session:
        result = await session.execute(select(ProviderStat))
        records = result.scalars().all()

    assert len(records) == 1
    record = records[0]
    assert record.agent_type == "internal"
    assert record.status == "completed"
    assert record.umo == "webchat:FriendMessage:session-42"
    assert record.conversation_id == "conv-123"
    assert record.provider_id == "provider-1"
    assert record.provider_model == "gpt-4.1"
    assert record.token_input_other == 11
    assert record.token_input_cached == 3
    assert record.token_output == 7
    assert record.start_time == 100.0
    assert record.end_time == 108.5
    assert record.time_to_first_token == 0.6


@pytest.mark.asyncio
async def test_record_internal_agent_stats_splits_failed_fallback_provider_usage(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(internal, "db_helper", temp_db)
    primary = SimpleNamespace(
        provider_config={"id": "primary"},
        meta=lambda: SimpleNamespace(id="primary", type="openai"),
        get_model=lambda: "primary-model",
    )
    fallback = SimpleNamespace(
        provider_config={"id": "fallback"},
        meta=lambda: SimpleNamespace(id="fallback", type="openai"),
        get_model=lambda: "fallback-model",
    )
    runner = SimpleNamespace(
        provider=fallback,
        stats=AgentStats(
            token_usage=TokenUsage(input_other=18, input_cached=4, output=11),
            start_time=100.0,
            end_time=108.0,
            time_to_first_token=5.0,
        ),
        provider_stat_segments=[
            ProviderStatSegment(
                provider=primary,
                usage=TokenUsage(input_other=8, input_cached=4, output=6),
                start_time=100.0,
                end_time=103.0,
            )
        ],
        was_aborted=lambda: False,
    )

    await internal._record_internal_agent_stats(
        SimpleNamespace(unified_msg_origin="test:session"),
        ProviderRequest(conversation=SimpleNamespace(cid="conv-1")),
        runner,
        SimpleNamespace(role="assistant"),
    )

    async with temp_db.get_db() as session:
        result = await session.execute(select(ProviderStat))
        records = sorted(result.scalars().all(), key=lambda item: item.provider_id)

    assert len(records) == 2
    fallback_record, primary_record = records
    assert fallback_record.provider_id == "fallback"
    assert fallback_record.status == "completed"
    assert fallback_record.token_input_other == 10
    assert fallback_record.token_input_cached == 0
    assert fallback_record.token_output == 5
    assert primary_record.provider_id == "primary"
    assert primary_record.status == "error"
    assert primary_record.token_input_other == 8
    assert primary_record.token_input_cached == 4
    assert primary_record.token_output == 6


@pytest.mark.asyncio
async def test_cancelled_agent_finally_schedules_stats_once(
    monkeypatch: pytest.MonkeyPatch,
):
    writer = AsyncMock()
    monkeypatch.setattr(internal, "_record_internal_agent_stats", writer)
    event = SimpleNamespace(unified_msg_origin="test:cancelled")
    request = ProviderRequest()
    runner = SimpleNamespace(get_final_llm_resp=lambda: None)
    started = asyncio.Event()

    async def cancelled_run() -> None:
        scheduled = False
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            scheduled = internal._schedule_internal_agent_stats(
                scheduled,
                event,
                request,
                runner,
                runner.get_final_llm_resp(),
            )
            internal._schedule_internal_agent_stats(
                scheduled,
                event,
                request,
                runner,
                runner.get_final_llm_resp(),
            )

    task = asyncio.create_task(cancelled_run())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    writer.assert_awaited_once_with(event, request, runner, None)
