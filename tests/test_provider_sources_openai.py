"""Smoke tests for ProviderOpenAIOfficial and its subclasses (openrouter, groq, zhipu, xai)."""
from unittest.mock import MagicMock, patch

from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.provider.sources.openrouter_source import ProviderOpenRouter
from astrbot.core.provider.sources.groq_source import ProviderGroq
from astrbot.core.provider.sources.zhipu_source import ProviderZhipu
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


@patch("astrbot.core.provider.sources.openai_source.create_proxy_client")
@patch("astrbot.core.provider.sources.openai_source.AsyncOpenAI")
def test_openrouter_injects_default_headers(mock_async_openai, mock_create_proxy):
    provider = ProviderOpenRouter(
        provider_config={"key": ["test-key"], "model": "openrouter-model"},
        provider_settings={},
    )
    assert provider.custom_headers is not None
    assert "HTTP-Referer" in provider.custom_headers
    assert "X-OpenRouter-Title" in provider.custom_headers


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
