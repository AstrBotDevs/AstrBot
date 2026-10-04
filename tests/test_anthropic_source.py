import json

import pytest
from anthropic import _base_client as anthropic_base_client
from anthropic.types import MessageDeltaUsage, Usage

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.entities import TokenUsage
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

# The SDK bundles its own httpx (``httpx`` before 1.0.0, ``httpx2`` after).
sdk_httpx = getattr(
    anthropic_base_client, "httpx", getattr(anthropic_base_client, "httpx2", None)
)


def _provider() -> ProviderAnthropic:
    return ProviderAnthropic.__new__(ProviderAnthropic)


def test_anthropic_extract_usage_counts_cache_creation_input():
    provider = _provider()

    usage = provider._extract_usage(
        Usage(
            input_tokens=10,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=50,
            output_tokens=20,
        )
    )

    # Anthropic's input_tokens excludes cache writes, so cache_creation
    # must be folded into input_other to keep total input accurate.
    assert usage.input_other == 60
    assert usage.input_cached == 100
    assert usage.input == 160
    assert usage.output == 20


def test_anthropic_extract_usage_without_cache_breakpoints():
    provider = _provider()

    usage = provider._extract_usage(Usage(input_tokens=30, output_tokens=10))

    assert usage.input_other == 30
    assert usage.input_cached == 0
    assert usage.input == 30
    assert usage.output == 10


def test_anthropic_extract_usage_none_returns_empty():
    provider = _provider()

    assert provider._extract_usage(None) == TokenUsage()


def test_anthropic_update_usage_counts_cache_creation_input():
    provider = _provider()
    token_usage = TokenUsage(input_other=5, input_cached=0, output=0)

    provider._update_usage(
        token_usage,
        MessageDeltaUsage(
            input_tokens=10,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=50,
            output_tokens=20,
        ),
    )

    assert token_usage.input_other == 60
    assert token_usage.input_cached == 100
    assert token_usage.input == 160
    assert token_usage.output == 20


def test_anthropic_update_usage_omitted_fields_are_preserved():
    provider = _provider()
    token_usage = TokenUsage(input_other=5, input_cached=0, output=0)

    # message_delta usage only carries output tokens in practice.
    provider._update_usage(token_usage, MessageDeltaUsage(output_tokens=7))

    assert token_usage.input_other == 5
    assert token_usage.input_cached == 0
    assert token_usage.output == 7


def _tool_use_stream(partial_json_chunks: list[str]) -> bytes:
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_01",
                "name": "get_time",
                "input": {},
            },
        },
        *(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": chunk},
            }
            for chunk in partial_json_chunks
        ),
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use", "stop_sequence": None},
            "usage": {"output_tokens": 5},
        },
        {"type": "message_stop"},
    ]
    return "".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
    ).encode()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunks", "expected_args"),
    [
        ([""], {}),
        (["", '{"tz": "UTC"}'], {"tz": "UTC"}),
    ],
)
async def test_anthropic_stream_keeps_tool_call_with_empty_input(
    monkeypatch, chunks, expected_args
):
    body = _tool_use_stream(chunks)
    transport = sdk_httpx.MockTransport(
        lambda request: sdk_httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=body
        )
    )
    monkeypatch.setattr(
        ProviderAnthropic,
        "_create_http_client",
        lambda self, provider_config: sdk_httpx.AsyncClient(transport=transport),
    )
    provider = ProviderAnthropic(
        {
            "id": "test",
            "type": "anthropic_chat_completion",
            "key": ["sk-test"],
            "model": "claude-test",
            "api_base": "https://api.anthropic.test",
        },
        {},
    )
    tools = ToolSet(
        [
            FunctionTool(
                name="get_time",
                description="Return the current time.",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )
    payloads = {
        "messages": [{"role": "user", "content": "what time is it?"}],
        "model": "claude-test",
    }

    try:
        responses = [r async for r in provider._query_stream(payloads, tools)]
    finally:
        await provider.terminate()

    tool_chunks = [r for r in responses if r.role == "tool"]
    assert len(tool_chunks) == 1
    final = responses[-1]
    assert not final.is_chunk
    for response in (tool_chunks[0], final):
        assert response.tools_call_name == ["get_time"]
        assert response.tools_call_args == [expected_args]
        assert response.tools_call_ids == ["toolu_01"]
