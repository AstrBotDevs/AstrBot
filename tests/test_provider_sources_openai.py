"""OpenAI-compatible adapter payload, reasoning, and header contracts."""

from unittest.mock import patch

import pytest
from openai.types.chat import ChatCompletion

from astrbot.core.provider.sources.groq_source import ProviderGroq
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.provider.sources.openrouter_source import ProviderOpenRouter
from astrbot.core.provider.sources.xai_source import ProviderXAI


@patch("astrbot.core.provider.sources.openai_source.create_proxy_client")
@patch("astrbot.core.provider.sources.openai_source.AsyncOpenAI")
def test_openai_construction(mock_async_openai, mock_create_proxy):
    provider = ProviderOpenAIOfficial(
        provider_config={"key": ["test-key"], "model": "gpt-4"},
        provider_settings={},
    )
    assert provider.get_model() == "gpt-4"
    assert provider.chosen_api_key == "test-key"
    assert mock_async_openai.call_args.kwargs["api_key"] == "test-key"
    assert mock_async_openai.call_args.kwargs["max_retries"] == 0


@patch("astrbot.core.provider.sources.openai_source.create_proxy_client")
@patch("astrbot.core.provider.sources.openai_source.AsyncOpenAI")
def test_openrouter_injects_default_headers(mock_async_openai, mock_create_proxy):
    ProviderOpenRouter(
        provider_config={
            "key": ["test-key"],
            "model": "openrouter-model",
            "custom_headers": {"X-Local": "keep"},
        },
        provider_settings={},
    )

    headers = mock_async_openai.call_args.kwargs["default_headers"]
    assert headers["HTTP-Referer"] == "https://github.com/AstrBotDevs/AstrBot"
    assert headers["X-OpenRouter-Title"] == "AstrBot"
    assert headers["X-OpenRouter-Categories"] == "general-chat,personal-agent"
    assert headers["X-Local"] == "keep"


@patch("astrbot.core.provider.sources.openai_source.create_proxy_client")
@patch("astrbot.core.provider.sources.openai_source.AsyncOpenAI")
def test_groq_strips_reasoning_content(mock_async_openai, mock_create_proxy):
    provider = ProviderGroq(
        provider_config={"key": ["test-key"], "model": "groq-model"},
        provider_settings={},
    )
    assert provider.reasoning_key == "reasoning"
    payloads = {
        "messages": [
            {"role": "assistant", "content": "hello", "reasoning_content": "think"},
            {"role": "user", "content": "hi"},
        ]
    }
    provider._finally_convert_payload(payloads)
    assert "reasoning_content" not in payloads["messages"][0]


@patch("astrbot.core.provider.sources.openai_source.create_proxy_client")
@patch("astrbot.core.provider.sources.openai_source.AsyncOpenAI")
def test_xai_search_injection_enabled(mock_async_openai, mock_create_proxy):
    provider = ProviderXAI(
        provider_config={
            "key": ["test-key"],
            "model": "grok-model",
            "xai_native_search": True,
        },
        provider_settings={},
    )
    payloads = {"messages": []}
    provider._maybe_inject_xai_search(payloads)
    assert payloads.get("search_parameters") == {"mode": "auto"}


@patch("astrbot.core.provider.sources.openai_source.create_proxy_client")
@patch("astrbot.core.provider.sources.openai_source.AsyncOpenAI")
def test_xai_search_injection_disabled(mock_async_openai, mock_create_proxy):
    provider = ProviderXAI(
        provider_config={
            "key": ["test-key"],
            "model": "grok-model",
            "xai_native_search": False,
        },
        provider_settings={},
    )
    payloads = {"messages": []}
    provider._maybe_inject_xai_search(payloads)
    assert "search_parameters" not in payloads


def test_sanitize_assistant_messages_filters_empty():
    payloads = {
        "messages": [
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "hello"},
        ]
    }
    ProviderOpenAIOfficial._sanitize_assistant_messages(payloads)
    assert len(payloads["messages"]) == 1
    assert payloads["messages"][0]["role"] == "user"


def test_sanitize_assistant_messages_preserves_tool_calls():
    payloads = {
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "foo"}}],
            },
        ]
    }
    ProviderOpenAIOfficial._sanitize_assistant_messages(payloads)
    assert len(payloads["messages"]) == 1
    assert payloads["messages"][0]["content"] is None


def test_truncate_error_text_candidate():
    text = "x" * 5000
    result = ProviderOpenAIOfficial._truncate_error_text_candidate(text)
    assert len(result) == 4096


def test_safe_json_dump():
    result = ProviderOpenAIOfficial._safe_json_dump({"key": "value"})
    assert result == '{"key": "value"}'


@pytest.mark.parametrize(
    ("details", "expected"),
    [
        (
            [
                {"type": "reasoning.summary", "summary": "Summary"},
                {"type": "reasoning.text", "text": "Details"},
            ],
            "Summary\n\nDetails",
        ),
        (
            [
                {"type": "reasoning.text", "text": "First "},
                {"type": "reasoning.text", "text": "second"},
            ],
            "First second",
        ),
        (
            [
                None,
                {},
                {"type": "reasoning.encrypted", "data": "opaque"},
                {"type": "reasoning.summary", "summary": "Visible"},
            ],
            "Visible",
        ),
    ],
)
@patch("astrbot.core.provider.sources.openai_source.create_proxy_client")
@patch("astrbot.core.provider.sources.openai_source.AsyncOpenAI")
def test_openrouter_replays_supported_reasoning_details_in_order(
    mock_async_openai, mock_create_proxy, details, expected
):
    provider = ProviderOpenRouter({"key": ["test-key"], "model": "router-model"}, {})
    completion = ChatCompletion.model_validate(
        {
            "id": "local-response",
            "object": "chat.completion",
            "created": 0,
            "model": "router-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "answer",
                        "reasoning_details": details,
                    },
                }
            ],
        }
    )

    assert provider._extract_reasoning_content(completion) == expected
