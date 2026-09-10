"""Cross-provider conversion of injected tool-call result pairs.

An injected pair (assistant with tool_calls + tool result) is structurally
identical to a real tool-call pair, so each provider must convert it through
the same native-format path. These tests lock in the conversion for the three
providers that do not speak the OpenAI chat format natively.

Anthropic:  tool_calls -> tool_use blocks, tool role -> tool_result block.
Gemini:     tool_calls -> functionCall part, tool role -> functionResponse part.
Responses:  tool_calls -> function_call item, tool role -> function_call_output.
"""

import pytest

from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)

INJECTED_PAIR_CONTEXT = [
    {"role": "system", "content": "system"},
    {"role": "user", "content": "history user"},
    {"role": "assistant", "content": "history bot"},
    {"role": "user", "content": "current question"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "fake_1",
                "type": "function",
                "function": {"name": "recall", "arguments": "{}"},
            }
        ],
    },
    {"role": "tool", "tool_call_id": "fake_1", "content": "memory json"},
]


@pytest.mark.asyncio
async def test_anthropic_payload_converts_injected_tool_calls_pair():
    provider = ProviderAnthropic(
        provider_config={
            "id": "test-anthropic",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
            "api_base": "https://api.anthropic.com",
        },
        provider_settings={},
    )
    try:
        system_prompt, new_messages = provider._prepare_payload(INJECTED_PAIR_CONTEXT)
    finally:
        await provider.terminate()

    assert system_prompt == "system"
    assert new_messages == [
        {"role": "user", "content": "history user"},
        {"role": "assistant", "content": [{"type": "text", "text": "history bot"}]},
        {"role": "user", "content": "current question"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "recall",
                    "input": {},
                    "id": "fake_1",
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "fake_1",
                    "content": "memory json",
                }
            ],
        },
    ]


@pytest.mark.asyncio
async def test_gemini_conversation_converts_injected_tool_calls_pair():
    provider = ProviderGoogleGenAI(
        provider_config={
            "id": "test-gemini",
            "type": "google_gemini",
            "model": "gemini-test",
            "key": ["test-key"],
            "api_base": "https://generativelanguage.googleapis.com",
        },
        provider_settings={},
    )
    try:
        contents = provider._prepare_conversation({"messages": INJECTED_PAIR_CONTEXT})
    finally:
        await provider.terminate()

    assert [c.role for c in contents] == ["user", "model", "user", "model", "user"]

    function_call_part = next(
        part
        for content in contents
        for part in content.parts
        if part.function_call is not None
    )
    assert function_call_part.function_call.name == "recall"
    assert function_call_part.function_call.args == {}

    function_response_part = next(
        part
        for content in contents
        for part in content.parts
        if part.function_response is not None
    )
    assert function_response_part.function_response.name == "fake_1"
    assert function_response_part.function_response.response == {
        "name": "fake_1",
        "content": "memory json",
    }


@pytest.mark.asyncio
async def test_responses_payload_converts_injected_tool_calls_pair():
    provider = ProviderOpenAIResponses(
        provider_config={
            "id": "test-responses",
            "provider": "openai",
            "type": "openai_responses",
            "model": "gpt-test",
            "key": ["test-key"],
            "api_base": "https://api.openai.com/v1",
        },
        provider_settings={},
    )
    try:
        response_input = provider._convert_chat_messages_to_response_input(
            INJECTED_PAIR_CONTEXT
        )
    finally:
        await provider.terminate()

    assert response_input == [
        {"type": "message", "role": "system", "content": "system"},
        {"type": "message", "role": "user", "content": "history user"},
        {"type": "message", "role": "assistant", "content": "history bot"},
        {"type": "message", "role": "user", "content": "current question"},
        {
            "type": "function_call",
            "call_id": "fake_1",
            "name": "recall",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "fake_1",
            "output": "memory json",
        },
    ]
