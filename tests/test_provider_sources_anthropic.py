"""Smoke tests for ProviderAnthropic."""
import pytest
from unittest.mock import patch

from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic


def test_anthropic_import():
    assert ProviderAnthropic is not None


@patch("astrbot.core.provider.sources.anthropic_source.create_proxy_client")
@patch("astrbot.core.provider.sources.anthropic_source.AsyncAnthropic")
def test_anthropic_construction(mock_async_anthropic, mock_create_proxy):
    provider = ProviderAnthropic(
        provider_config={
            "key": ["test-key"],
            "model": "claude-sonnet-4-20250514",
        },
        provider_settings={},
        use_api_key=False,
    )
    assert provider.get_model() == "claude-sonnet-4-20250514"
    assert provider.base_url == "https://api.anthropic.com"


@patch("astrbot.core.provider.sources.anthropic_source.create_proxy_client")
@patch("astrbot.core.provider.sources.anthropic_source.AsyncAnthropic")
def test_anthropic_construction_with_api_key(mock_async_anthropic, mock_create_proxy):
    provider = ProviderAnthropic(
        provider_config={
            "key": ["test-key"],
            "model": "claude-sonnet-4-20250514",
        },
        provider_settings={},
    )
    assert provider.chosen_api_key == "test-key"


def test_anthropic_empty_output_raises_error():
    llm_response = LLMResponse(role="assistant")
    with pytest.raises(EmptyModelOutputError):
        ProviderAnthropic._ensure_usable_response(
            llm_response,
            completion_id="msg_empty",
            stop_reason="end_turn",
        )


def test_anthropic_reasoning_output_is_allowed():
    llm_response = LLMResponse(
        role="assistant",
        reasoning_content="chain of thought",
    )
    ProviderAnthropic._ensure_usable_response(
        llm_response,
        completion_id="msg_reasoning",
        stop_reason="end_turn",
    )


def test_normalize_custom_headers():
    headers = ProviderAnthropic._normalize_custom_headers(
        {"custom_headers": {"X-Test": "value", "X-Num": 42}}
    )
    assert headers == {"X-Test": "value", "X-Num": "42"}


def test_normalize_custom_headers_none_on_empty():
    assert ProviderAnthropic._normalize_custom_headers({}) is None
