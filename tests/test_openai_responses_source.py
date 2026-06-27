import json
from types import SimpleNamespace

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)


class _Responses:
    async def create(self, **kwargs):
        return SimpleNamespace(output_text="ok", output=[], usage=None)


class _Client:
    def __init__(self) -> None:
        self.responses = _Responses()


def _make_provider() -> ProviderOpenAIResponses:
    provider = ProviderOpenAIResponses.__new__(ProviderOpenAIResponses)
    provider.client = _Client()
    provider.default_params = {
        "model",
        "input",
        "tools",
        "tool_choice",
        "stream",
        "extra_body",
    }
    provider.provider_config = {"custom_extra_body": {"metadata": {"test": True}}}
    provider._apply_provider_specific_extra_body_overrides = lambda extra_body: None
    return provider


def _make_tool_set() -> ToolSet:
    return ToolSet(
        tools=[
            FunctionTool(
                name="lookup_weather",
                description="Look up weather",
                parameters={
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            )
        ]
    )


def test_chat_payload_to_responses_payload_converts_messages_and_tool_calls():
    payload = {
        "model": "gpt-4.1",
        "messages": [
            {"role": "system", "content": "Be brief."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "weather"},
                    {"type": "image_url", "image_url": {"url": "data:image/png,abc"}},
                ],
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "lookup_weather",
                            "arguments": {"city": "Shanghai"},
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
        ],
    }

    converted = ProviderOpenAIResponses._chat_payload_to_responses_payload(payload)

    assert "messages" not in converted
    assert converted["model"] == "gpt-4.1"
    assert converted["input"] == [
        {"role": "system", "content": "Be brief."},
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "weather"},
                {"type": "input_image", "image_url": "data:image/png,abc"},
            ],
        },
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "lookup_weather",
            "arguments": '{"city": "Shanghai"}',
            "status": "completed",
        },
        {"type": "function_call_output", "call_id": "call_1", "output": "sunny"},
    ]


def test_chat_payload_to_responses_payload_replaces_audio_parts_with_placeholder():
    payload = {
        "model": "gpt-4.1",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "listen"},
                    {
                        "type": "input_audio",
                        "input_audio": {"data": "abc", "format": "wav"},
                    },
                    {"type": "audio_url", "audio_url": {"url": "data:audio/wav,abc"}},
                ],
            },
        ],
    }

    converted = ProviderOpenAIResponses._chat_payload_to_responses_payload(payload)

    assert converted["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "listen"},
                {"type": "input_text", "text": "[Audio]"},
                {"type": "input_text", "text": "[Audio]"},
            ],
        },
    ]


def test_chat_payload_to_responses_payload_preserves_reasoning_items():
    reasoning_item = {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [{"type": "summary_text", "text": "checked options"}],
        "content": [{"type": "reasoning_text", "text": "private trace"}],
        "encrypted_content": "encrypted-reasoning",
        "status": "completed",
    }
    payload = {
        "model": "gpt-5",
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "think",
                        "think": "private trace",
                        "encrypted": json.dumps(reasoning_item),
                    },
                    {"type": "text", "text": "answer"},
                ],
            },
        ],
    }

    converted = ProviderOpenAIResponses._chat_payload_to_responses_payload(payload)

    assert converted["input"] == [
        reasoning_item,
        {
            "role": "assistant",
            "content": [{"type": "output_text", "text": "answer"}],
        },
    ]


def test_build_responses_request_shares_tool_and_extra_body_handling():
    provider = _make_provider()
    payload = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "hello"}],
        "unknown_param": "kept-in-extra-body",
    }

    request_payload, extra_body = provider._build_responses_request(
        payload,
        _make_tool_set(),
    )

    assert request_payload["input"] == [{"role": "user", "content": "hello"}]
    assert request_payload["tool_choice"] == "auto"
    assert request_payload["tools"] == [
        {
            "type": "function",
            "name": "lookup_weather",
            "description": "Look up weather",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
            "strict": False,
        }
    ]
    assert extra_body == {
        "metadata": {"test": True},
        "unknown_param": "kept-in-extra-body",
    }


@pytest.mark.asyncio
async def test_parse_responses_completion_extracts_function_call_and_usage():
    provider = _make_provider()
    response = SimpleNamespace(
        id="resp_1",
        output=[
            SimpleNamespace(
                type="function_call",
                name="lookup_weather",
                call_id="call_1",
                arguments='{"city":"Guangzhou"}',
            )
        ],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=3,
            input_tokens_details=SimpleNamespace(cached_tokens=4),
        ),
    )

    result = await provider._parse_responses_completion(response, _make_tool_set())

    assert result.role == "tool"
    assert result.tools_call_name == ["lookup_weather"]
    assert result.tools_call_ids == ["call_1"]
    assert result.tools_call_args == [{"city": "Guangzhou"}]
    assert result.usage.input_other == 6
    assert result.usage.input_cached == 4
    assert result.usage.output == 3


@pytest.mark.asyncio
async def test_parse_responses_completion_preserves_reasoning_item():
    provider = _make_provider()
    reasoning_item = {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [{"type": "summary_text", "text": "checked options"}],
        "content": [{"type": "reasoning_text", "text": "private trace"}],
        "encrypted_content": "encrypted-reasoning",
        "status": "completed",
    }
    response = {
        "id": "resp_1",
        "output": [
            reasoning_item,
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "answer"}],
            },
        ],
        "usage": None,
    }

    result = await provider._parse_responses_completion(response, None)

    assert result.completion_text == "answer"
    assert result.reasoning_content == "private trace"
    assert json.loads(result.reasoning_signature) == reasoning_item


@pytest.mark.asyncio
async def test_stream_function_call_events_are_converted_to_tool_response():
    provider = _make_provider()
    function_calls: dict[str, dict] = {}

    ProviderOpenAIResponses._merge_stream_function_call_event(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "type": "function_call",
                "name": "lookup_weather",
                "call_id": "call_1",
            },
        },
        function_calls,
    )
    ProviderOpenAIResponses._merge_stream_function_call_event(
        {
            "type": "response.function_call_arguments.delta",
            "output_index": 0,
            "delta": '{"city"',
        },
        function_calls,
    )
    ProviderOpenAIResponses._merge_stream_function_call_event(
        {
            "type": "response.function_call_arguments.delta",
            "output_index": 0,
            "delta": ':"Shanghai"}',
        },
        function_calls,
    )

    result = await provider._stream_function_calls_to_response(
        function_calls,
        _make_tool_set(),
    )

    assert result.role == "tool"
    assert result.tools_call_name == ["lookup_weather"]
    assert result.tools_call_ids == ["call_1"]
    assert result.tools_call_args == [{"city": "Shanghai"}]
