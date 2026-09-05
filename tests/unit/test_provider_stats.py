import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from astrbot.core.agent.response import AgentStats
from astrbot.core.db.po import ProviderStat
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.provider.entities import ProviderRequest, TokenUsage
from astrbot.core.provider.stats import (
    ProviderStatSegment,
    record_agent_runner_stats,
    record_llm_response_stats,
)


def assert_public_token_usage(token_usage: dict[str, int]) -> None:
    assert token_usage == {
        "input_other": 5,
        "input_cached": 2,
        "output": 3,
    }


@pytest.mark.asyncio
async def test_record_llm_response_stats_only_passes_public_token_fields():
    usage = TokenUsage(input_other=5, input_cached=2, output=3)
    usage.internal_note = "must not reach the database"
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = SimpleNamespace(
        provider_config={"id": "provider-1"},
        meta=lambda: SimpleNamespace(id="provider-1"),
        get_model=lambda: "test-model",
    )

    await record_llm_response_stats(
        db,
        umo="provider:provider-1:test",
        provider=provider,
        response=SimpleNamespace(role="assistant", usage=usage),
        start_time=100.0,
        end_time=101.0,
    )

    stats = db.insert_provider_stat.await_args.kwargs["stats"]
    assert_public_token_usage(stats["token_usage"])


@pytest.mark.asyncio
async def test_record_llm_response_stats_uses_explicit_failure_usage():
    usage = TokenUsage(input_other=5, input_cached=2, output=3)
    usage.internal_note = "must not reach the database"
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = SimpleNamespace(
        provider_config={"id": "provider-1"},
        meta=lambda: SimpleNamespace(id="provider-1"),
        get_model=lambda: "test-model",
    )

    await record_llm_response_stats(
        db,
        umo="provider:provider-1:failed",
        provider=provider,
        response=None,
        usage=usage,
        start_time=100.0,
        end_time=101.0,
    )

    stats = db.insert_provider_stat.await_args.kwargs["stats"]
    assert_public_token_usage(stats["token_usage"])


@pytest.mark.asyncio
async def test_record_agent_runner_stats_only_passes_public_segment_token_fields():
    usage = TokenUsage(input_other=5, input_cached=2, output=3)
    usage.internal_note = "must not reach the database"
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = SimpleNamespace(
        provider_config={"id": "provider-1"},
        meta=lambda: SimpleNamespace(id="provider-1"),
        get_model=lambda: "test-model",
    )
    runner = SimpleNamespace(
        provider=provider,
        stats=AgentStats(
            token_usage=usage,
            start_time=100.0,
            end_time=102.0,
        ),
        provider_stat_segments=[
            ProviderStatSegment(
                provider=provider,
                usage=usage,
                start_time=100.0,
                end_time=101.0,
            )
        ],
        was_aborted=lambda: False,
    )

    await record_agent_runner_stats(
        db,
        umo="test:session",
        request=None,
        agent_runner=runner,
        final_response=SimpleNamespace(role="assistant"),
    )

    segment_stats = db.insert_provider_stat.await_args_list[0].kwargs["stats"]
    assert_public_token_usage(segment_stats["token_usage"])


@pytest.mark.asyncio
async def test_record_agent_runner_stats_observes_end_time_for_cancelled_runner():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = SimpleNamespace(
        provider_config={"id": "provider-1"},
        meta=lambda: SimpleNamespace(id="provider-1"),
        get_model=lambda: "test-model",
    )
    stats = AgentStats(
        token_usage=TokenUsage(),
        start_time=100.0,
        end_time=0.0,
    )
    runner = SimpleNamespace(
        provider=provider,
        stats=stats,
        provider_stat_segments=[],
        was_aborted=lambda: True,
    )

    await record_agent_runner_stats(
        db,
        umo="test:cancelled-before-response",
        request=None,
        agent_runner=runner,
        final_response=None,
    )

    call = db.insert_provider_stat.await_args.kwargs
    assert call["status"] == "aborted"
    assert call["stats"]["end_time"] >= call["stats"]["start_time"]
    assert stats.end_time == 0.0


@pytest.mark.asyncio
async def test_record_agent_runner_stats_normalizes_end_after_segment_start():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    primary = SimpleNamespace(
        provider_config={"id": "primary"},
        meta=lambda: SimpleNamespace(id="primary"),
        get_model=lambda: "primary-model",
    )
    fallback = SimpleNamespace(
        provider_config={"id": "fallback"},
        meta=lambda: SimpleNamespace(id="fallback"),
        get_model=lambda: "fallback-model",
    )
    stats = AgentStats(
        token_usage=TokenUsage(input_other=13),
        start_time=100.0,
        end_time=110.0,
    )
    runner = SimpleNamespace(
        provider=fallback,
        stats=stats,
        provider_stat_segments=[
            ProviderStatSegment(
                provider=primary,
                usage=TokenUsage(input_other=13),
                start_time=100.0,
                end_time=120.0,
            )
        ],
        was_aborted=lambda: True,
    )

    await record_agent_runner_stats(
        db,
        umo="test:cancelled-after-fallback",
        request=None,
        agent_runner=runner,
        final_response=None,
    )

    final_call = db.insert_provider_stat.await_args_list[-1].kwargs
    assert final_call["provider_id"] == "fallback"
    assert final_call["status"] == "aborted"
    assert final_call["stats"]["start_time"] == 120.0
    assert final_call["stats"]["end_time"] >= 120.0
    assert stats.end_time == 110.0


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
