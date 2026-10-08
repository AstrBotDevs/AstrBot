import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.response import AgentStats
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.provider.provider import provider_stats_managed_by_agent
from astrbot.core.provider.stats import (
    ProviderStatSegment,
    record_agent_runner_stats,
    record_llm_response_stats,
)
from astrbot.core.provider.usage_recorder import (
    event_usage_scope,
    instrument_provider,
    usage_scope,
)


def _provider(provider_id="primary", *, response=None):
    response = response or LLMResponse(
        role="assistant", usage=TokenUsage(input_other=8, input_cached=3, output=2)
    )

    async def text_chat(**kwargs):
        assert provider_stats_managed_by_agent.get() is True
        return response

    async def text_chat_stream(**kwargs):
        assert provider_stats_managed_by_agent.get() is True
        yield response

    return SimpleNamespace(
        provider_config={"id": provider_id, "provider_source_id": "source-a"},
        get_model=lambda: "default-model",
        text_chat=text_chat,
        text_chat_stream=text_chat_stream,
    )


@pytest.mark.asyncio
async def test_two_direct_calls_have_distinct_ids_and_real_session_attribution():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider()
    instrument_provider(provider, db)
    event = SimpleNamespace(
        unified_msg_origin="qq:GroupMessage:42",
        trace=SimpleNamespace(span_id="trace-42"),
    )
    with event_usage_scope(event, plugin_id="plugin-a"):
        await provider.text_chat(model="requested-model")
        with usage_scope(request_kind="compression"):
            await provider.text_chat(model="requested-model")

    assert db.insert_provider_stat.await_count == 2
    first, second = (call.kwargs for call in db.insert_provider_stat.await_args_list)
    assert first["umo"] == "qq:GroupMessage:42"
    assert first["stats"]["session_umo"] == "qq:GroupMessage:42"
    assert first["stats"]["source_id"] == "source-a"
    assert first["stats"]["trace_id"] == "trace-42"
    assert first["stats"]["plugin_id"] == "plugin-a"
    assert first["stats"]["usage_status"] == "reported"
    assert first["stats"]["request_id"] != second["stats"]["request_id"]
    assert first["stats"]["request_kind"] == "text"
    assert second["stats"]["request_kind"] == "compression"
    assert first["stats"]["token_usage"] == {
        "input_other": 8,
        "input_cached": 3,
        "output": 2,
    }


@pytest.mark.asyncio
async def test_missing_usage_and_explicit_zero_are_distinct():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider(response=LLMResponse(role="assistant", usage=None))
    instrument_provider(provider, db)
    await provider.text_chat()
    assert (
        db.insert_provider_stat.await_args.kwargs["stats"]["usage_status"] == "missing"
    )

    provider.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", usage=TokenUsage())
    )
    instrument_provider(provider, db)
    await provider.text_chat()
    assert (
        db.insert_provider_stat.await_args.kwargs["stats"]["usage_status"] == "reported"
    )


@pytest.mark.asyncio
async def test_provider_marked_partial_usage_remains_partial():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    usage = TokenUsage(input_other=5)
    usage.is_partial = True
    provider = _provider(response=LLMResponse(role="assistant", usage=usage))
    instrument_provider(provider, db)
    await provider.text_chat()
    assert (
        db.insert_provider_stat.await_args.kwargs["stats"]["usage_status"] == "partial"
    )


@pytest.mark.asyncio
async def test_nested_same_provider_suppressed_but_fallback_provider_recorded():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    primary = _provider("primary")
    fallback = _provider("fallback")
    nested_once = False

    async def nested(**kwargs):
        nonlocal nested_once
        if not nested_once:
            nested_once = True
            await primary.text_chat()
        await fallback.text_chat()
        return LLMResponse(role="assistant", usage=TokenUsage(input_other=1))

    primary.text_chat = nested
    instrument_provider(primary, db)
    instrument_provider(fallback, db)
    with usage_scope(session_umo="qq:GroupMessage:1", trace_id="trace-1"):
        await primary.text_chat()
    assert [
        c.kwargs["provider_id"] for c in db.insert_provider_stat.await_args_list
    ] == [
        "fallback",
        "fallback",
        "primary",
    ]


@pytest.mark.asyncio
async def test_child_task_on_same_provider_is_a_separate_call():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider()

    async def spawning(**kwargs):
        if kwargs.get("spawn"):
            await asyncio.create_task(provider.text_chat())
        return LLMResponse(role="assistant", usage=TokenUsage(input_other=1))

    provider.text_chat = spawning
    instrument_provider(provider, db)
    await provider.text_chat(spawn=True)
    assert db.insert_provider_stat.await_count == 2


@pytest.mark.asyncio
async def test_none_response_is_error_with_missing_usage():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider()
    provider.text_chat = AsyncMock(return_value=None)
    instrument_provider(provider, db)
    assert await provider.text_chat() is None
    call = db.insert_provider_stat.await_args.kwargs
    assert call["status"] == "error"
    assert call["stats"]["usage_status"] == "missing"


@pytest.mark.asyncio
async def test_stream_cancel_records_partial_usage_once_without_context_leak():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider(
        response=LLMResponse(
            role="assistant", usage=TokenUsage(input_other=8), is_chunk=True
        )
    )
    instrument_provider(provider, db)
    assert inspect.isasyncgenfunction(provider.text_chat_stream)
    assert inspect.signature(provider.text_chat_stream) == inspect.signature(
        _provider().text_chat_stream
    )
    with usage_scope(session_umo="qq:GroupMessage:7"):
        stream = provider.text_chat_stream()
        first = await anext(stream)
        assert first.usage.input_other == 8
        assert provider_stats_managed_by_agent.get() is False
        await stream.aclose()
    db.insert_provider_stat.assert_awaited_once()
    call = db.insert_provider_stat.await_args.kwargs
    assert call["status"] == "aborted"
    assert call["stats"]["usage_status"] == "partial"


@pytest.mark.asyncio
async def test_stream_close_without_reported_usage_is_missing():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider(
        response=LLMResponse(role="assistant", usage=None, is_chunk=True)
    )
    instrument_provider(provider, db)
    stream = provider.text_chat_stream()
    await anext(stream)
    await stream.aclose()
    assert db.insert_provider_stat.await_args.kwargs["status"] == "aborted"
    assert (
        db.insert_provider_stat.await_args.kwargs["stats"]["usage_status"] == "missing"
    )


@pytest.mark.asyncio
async def test_stream_error_keeps_latest_known_usage():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider()

    async def failing_stream(**kwargs):
        yield LLMResponse(
            role="assistant", usage=TokenUsage(input_other=6), is_chunk=True
        )
        raise RuntimeError("stream interrupted")

    provider.text_chat_stream = failing_stream
    instrument_provider(provider, db)
    stream = provider.text_chat_stream()
    await anext(stream)
    with pytest.raises(RuntimeError, match="stream interrupted"):
        await anext(stream)
    call = db.insert_provider_stat.await_args.kwargs
    assert call["status"] == "error"
    assert call["stats"]["usage_status"] == "partial"
    assert call["stats"]["token_usage"]["input_other"] == 6


@pytest.mark.asyncio
async def test_stream_task_cancellation_records_partial_usage():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider()

    async def slow_stream(**kwargs):
        yield LLMResponse(
            role="assistant", usage=TokenUsage(input_other=6), is_chunk=True
        )
        await asyncio.sleep(60)

    provider.text_chat_stream = slow_stream
    instrument_provider(provider, db)
    stream = provider.text_chat_stream()
    await anext(stream)
    task = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    call = db.insert_provider_stat.await_args.kwargs
    assert call["status"] == "aborted"
    assert call["stats"]["usage_status"] == "partial"
    assert call["stats"]["token_usage"]["input_other"] == 6


@pytest.mark.asyncio
async def test_stream_close_after_final_response_is_completed():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider()
    instrument_provider(provider, db)
    stream = provider.text_chat_stream()
    final = await anext(stream)
    assert final.is_chunk is False
    await stream.aclose()
    call = db.insert_provider_stat.await_args.kwargs
    assert call["status"] == "completed"
    assert call["stats"]["usage_status"] == "reported"


@pytest.mark.asyncio
async def test_stream_eof_without_final_response_is_error_with_partial_usage():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider()

    async def truncated_stream(**kwargs):
        yield LLMResponse(
            role="assistant", usage=TokenUsage(input_other=5), is_chunk=True
        )

    provider.text_chat_stream = truncated_stream
    instrument_provider(provider, db)
    responses = [response async for response in provider.text_chat_stream()]
    assert len(responses) == 1
    call = db.insert_provider_stat.await_args.kwargs
    assert call["status"] == "error"
    assert call["stats"]["usage_status"] == "partial"


@pytest.mark.asyncio
async def test_stream_keeps_first_consumer_attribution_across_later_scopes():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider("outer")
    nested = _provider("nested")

    async def source_stream(**kwargs):
        yield LLMResponse(role="assistant", is_chunk=True)
        await nested.text_chat()
        yield LLMResponse(
            role="assistant", usage=TokenUsage(input_other=4), is_chunk=False
        )

    provider.text_chat_stream = source_stream
    instrument_provider(provider, db)
    instrument_provider(nested, db)
    with usage_scope(session_umo="qq:GroupMessage:A", plugin_id="plugin-A"):
        stream = provider.text_chat_stream()
        await asyncio.create_task(anext(stream))
    with usage_scope(session_umo="qq:GroupMessage:B", plugin_id="plugin-B"):
        await asyncio.create_task(anext(stream))
        await asyncio.create_task(stream.aclose())
    assert db.insert_provider_stat.await_count == 2
    for call in db.insert_provider_stat.await_args_list:
        assert call.kwargs["umo"] == "qq:GroupMessage:A"
        assert call.kwargs["stats"]["plugin_id"] == "plugin-A"


@pytest.mark.asyncio
async def test_error_usage_and_database_failure_preserve_business_result():
    db = SimpleNamespace(
        insert_provider_stat=AsyncMock(side_effect=RuntimeError("db down"))
    )
    provider = _provider()

    async def failed(**kwargs):
        exc = RuntimeError("provider down")
        exc._astrbot_token_usage = TokenUsage(input_other=4)
        raise exc

    provider.text_chat = failed
    instrument_provider(provider, db)
    with pytest.raises(RuntimeError, match="provider down"):
        await provider.text_chat()
    call = db.insert_provider_stat.await_args.kwargs
    assert call["status"] == "error"
    assert call["stats"]["token_usage"]["input_other"] == 4


@pytest.mark.asyncio
async def test_concurrent_scope_attribution_does_not_leak():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider()
    instrument_provider(provider, db)

    async def call(group, plugin):
        with usage_scope(session_umo=group, plugin_id=plugin):
            await asyncio.sleep(0)
            await provider.text_chat()

    await asyncio.gather(
        call("qq:GroupMessage:1", "plugin-1"),
        call("qq:GroupMessage:2", "plugin-2"),
    )
    assert {
        (c.kwargs["umo"], c.kwargs["stats"]["plugin_id"])
        for c in db.insert_provider_stat.await_args_list
    } == {
        ("qq:GroupMessage:1", "plugin-1"),
        ("qq:GroupMessage:2", "plugin-2"),
    }


@pytest.mark.asyncio
async def test_event_scope_without_event_retains_outer_plugin_and_session():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider()
    instrument_provider(provider, db)
    with usage_scope(session_umo="qq:GroupMessage:9", plugin_id="plugin-9"):
        with event_usage_scope(None):
            await provider.text_chat()
    call = db.insert_provider_stat.await_args.kwargs
    assert call["umo"] == "qq:GroupMessage:9"
    assert call["stats"]["plugin_id"] == "plugin-9"


@pytest.mark.asyncio
async def test_instrumented_provider_suppresses_legacy_aggregate_writers():
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    provider = _provider()
    instrument_provider(provider, db)
    await record_llm_response_stats(
        db,
        umo="qq:GroupMessage:1",
        provider=provider,
        response=LLMResponse(role="assistant", usage=TokenUsage(input_other=3)),
        start_time=1.0,
        end_time=2.0,
    )
    runner = SimpleNamespace(
        provider=provider,
        stats=SimpleNamespace(token_usage=TokenUsage(input_other=3)),
        provider_stat_segments=[],
    )
    await record_agent_runner_stats(
        db,
        umo="qq:GroupMessage:1",
        request=None,
        agent_runner=runner,
        final_response=None,
    )
    db.insert_provider_stat.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wrapped_final", "expected_provider", "expected_input"),
    [(True, "fallback", 7), (False, "primary", 3)],
)
async def test_mixed_fallback_records_only_unwrapped_provider_remainder(
    wrapped_final, expected_provider, expected_input
):
    db = SimpleNamespace(insert_provider_stat=AsyncMock())
    primary = _provider("primary")
    fallback = _provider("fallback")
    instrument_provider(primary if wrapped_final else fallback, db)
    runner = SimpleNamespace(
        provider=primary,
        stats=AgentStats(
            token_usage=TokenUsage(input_other=10), start_time=1.0, end_time=3.0
        ),
        provider_stat_segments=[
            ProviderStatSegment(
                provider=fallback,
                usage=TokenUsage(input_other=7),
                start_time=1.0,
                end_time=2.0,
            )
        ],
        was_aborted=lambda: False,
    )
    await record_agent_runner_stats(
        db,
        umo="qq:GroupMessage:1",
        request=None,
        agent_runner=runner,
        final_response=LLMResponse(role="assistant"),
    )
    db.insert_provider_stat.assert_awaited_once()
    call = db.insert_provider_stat.await_args.kwargs
    assert call["provider_id"] == expected_provider
    assert call["stats"]["token_usage"]["input_other"] == expected_input
