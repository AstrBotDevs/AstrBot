"""Anthropic configuration, header normalization, and response contracts."""

from unittest.mock import patch

import pytest

from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic


def test_header_normalization_keeps_the_callers_configuration_unchanged():
    configuration = {"custom_headers": {"X-Count": 42}}
    normalized = ProviderAnthropic._normalize_custom_headers(configuration)

    assert normalized == {"X-Count": "42"}
    normalized["X-New"] = "local"
    assert configuration == {"custom_headers": {"X-Count": 42}}


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
    mock_async_anthropic.assert_not_called()


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
    mock_async_anthropic.assert_called_once()


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
