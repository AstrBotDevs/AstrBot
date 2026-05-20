from types import SimpleNamespace

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent.message import AssistantMessageSegment, ToolCallMessageSegment
from astrbot.core.provider.entities import ToolCallsResult
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)


class _FakeResponsesClient:
    def __init__(self, response=None, stream=None):
        self.calls = []
        self._response = response
        self._stream = stream

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return self._stream
        return self._response


class _FakeAsyncStream:
    def __init__(self, events):
        self._events = events

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for event in self._events:
            yield event


def _event(event_type: str, **kwargs):
    return SimpleNamespace(type=event_type, **kwargs)


def _make_provider(overrides: dict | None = None) -> ProviderOpenAIResponses:
    provider_config = {
        "id": "test-responses",
        "type": "openai_responses",
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "key": ["test-key"],
        "api_base": "https://api.openai.com/v1",
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderOpenAIResponses(
        provider_config=provider_config,
        provider_settings={},
    )


@pytest.mark.asyncio
async def test_responses_non_stream_converts_messages_to_input():
    provider = _make_provider()
    response = SimpleNamespace(
        id="resp_1",
        output_text="final answer",
        usage=SimpleNamespace(input_tokens=7, output_tokens=3),
    )
    provider.client.responses = _FakeResponsesClient(response=response)
    try:
        result = await provider.text_chat(
            prompt="hello",
            contexts=[{"role": "assistant", "content": "previous"}],
            system_prompt="system prompt",
        )

        call = provider.client.responses.calls[0]
        assert call["model"] == "gpt-4.1-mini"
        assert call["input"] == [
            {"role": "system", "content": "system prompt"},
            {"role": "assistant", "content": "previous"},
            {"role": "user", "content": "hello"},
        ]
        assert result.completion_text == "final answer"
        assert result.id == "resp_1"
        assert result.usage.input == 7
        assert result.usage.output == 3
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_responses_does_not_handle_xai_native_search():
    provider = _make_provider(
        {
            "provider": "xai",
            "xai_native_search": True,
            "allowed_domains": ["example.com"],
            "enable_image_understanding": True,
        }
    )
    provider.client.responses = _FakeResponsesClient(
        response=SimpleNamespace(id="resp_1", output_text="ok", usage=None)
    )
    try:
        await provider.text_chat(prompt="search")

        assert "tools" not in provider.client.responses.calls[0]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_responses_stream_yields_deltas_and_final_response():
    provider = _make_provider()
    provider.client.responses = _FakeResponsesClient(
        stream=_FakeAsyncStream(
            [
                _event("response.output_text.delta", delta="hel"),
                _event("response.output_text.delta", delta="lo"),
                _event("response.output_text.done", text="hello"),
                _event("response.completed", response=SimpleNamespace(id="resp_2")),
            ]
        )
    )
    try:
        chunks = [
            chunk
            async for chunk in provider.text_chat_stream(prompt="stream please")
        ]

        assert [chunk.completion_text for chunk in chunks] == ["hel", "lo", "hello"]
        assert chunks[0].is_chunk is True
        assert chunks[-1].is_chunk is False
        assert chunks[-1].id == "resp_2"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_responses_function_tools_are_flat_function_schemas():
    provider = _make_provider()
    provider.client.responses = _FakeResponsesClient(
        response=SimpleNamespace(id="resp_1", output_text="ok", usage=None)
    )
    tool_set = ToolSet(
        [
            FunctionTool(
                name="lookup",
                description="Lookup an item",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                handler=None,
            )
        ]
    )
    try:
        await provider.text_chat(prompt="use tool", func_tool=tool_set)

        assert provider.client.responses.calls[0]["tools"] == [
            {
                "type": "function",
                "name": "lookup",
                "strict": False,
                "description": "Lookup an item",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_responses_uses_custom_extra_body():
    provider = _make_provider(
        {
            "custom_extra_body": {
                "reasoning": {"effort": "high"},
                "store": False,
            }
        }
    )
    provider.client.responses = _FakeResponsesClient(
        response=SimpleNamespace(id="resp_1", output_text="ok", usage=None)
    )
    try:
        await provider.text_chat(prompt="hello")

        assert provider.client.responses.calls[0]["extra_body"] == {
            "reasoning": {"effort": "high"},
            "store": False,
        }
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_responses_ignores_legacy_response_extra_body():
    provider = _make_provider(
        {
            "response_extra_body": {"store": False},
        }
    )
    provider.client.responses = _FakeResponsesClient(
        response=SimpleNamespace(id="resp_1", output_text="ok", usage=None)
    )
    try:
        await provider.text_chat(prompt="hello")

        assert provider.client.responses.calls[0]["extra_body"] == {}
    finally:
        await provider.terminate()


def test_responses_input_converts_assistant_tool_calls_to_function_call_items():
    input_items = ProviderOpenAIResponses._messages_to_response_input(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "lookup",
                            "arguments": '{"query":"weather"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": '{"temperature":21}',
            },
        ]
    )

    assert input_items == [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "lookup",
            "arguments": '{"query":"weather"}',
            "status": "completed",
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"temperature":21}',
        },
    ]
    assert all("tool_calls" not in item for item in input_items)


def test_responses_input_preserves_assistant_text_before_function_call_items():
    input_items = ProviderOpenAIResponses._messages_to_response_input(
        [
            {
                "role": "assistant",
                "content": "I will check.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": "{}"},
                    }
                ],
            }
        ]
    )

    assert input_items == [
        {"role": "assistant", "content": "I will check."},
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "lookup",
            "arguments": "{}",
            "status": "completed",
        },
    ]
    assert all("tool_calls" not in item for item in input_items)


@pytest.mark.asyncio
async def test_responses_stream_tool_call_history_uses_function_call_items():
    provider = _make_provider()
    provider.client.responses = _FakeResponsesClient(
        stream=_FakeAsyncStream(
            [
                _event(
                    "response.completed",
                    response=SimpleNamespace(id="resp_2", output_text="done"),
                )
            ]
        )
    )
    tool_call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "lookup", "arguments": '{"query":"weather"}'},
    }
    try:
        chunks = [
            chunk
            async for chunk in provider.text_chat_stream(
                prompt="continue",
                tool_calls_result=ToolCallsResult(
                    tool_calls_info=AssistantMessageSegment(
                        content=None,
                        tool_calls=[tool_call],
                    ),
                    tool_calls_result=[
                        ToolCallMessageSegment(
                            content='{"temperature":21}',
                            tool_call_id="call_1",
                        )
                    ],
                ),
            )
        ]

        call = provider.client.responses.calls[0]
        assert chunks[-1].completion_text == "done"
        assert all("tool_calls" not in item for item in call["input"])
        assert call["input"][-3:] == [
            {"role": "user", "content": "continue"},
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": '{"query":"weather"}',
                "status": "completed",
            },
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": '{"temperature":21}',
            },
        ]
    finally:
        await provider.terminate()
