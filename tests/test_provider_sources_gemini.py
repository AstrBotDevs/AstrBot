"""Gemini warning filtering, client configuration, and response contracts."""

import logging
from unittest.mock import patch

import pytest

from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.gemini_source import (
    ProviderGoogleGenAI,
    SuppressNonTextPartsWarning,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("there are non-text parts in the response", False),
        ("there are non-text parts in the response: image", False),
        ("some other warning", True),
        ("request failed with HTTP 503", True),
    ],
)
def test_suppress_non_text_parts_warning_filter(message, expected):
    record = logging.LogRecord(
        "google.genai", logging.WARNING, __file__, 1, message, (), None
    )

    assert SuppressNonTextPartsWarning().filter(record) is expected


def test_gemini_categories_and_thresholds():
    assert "harassment" in ProviderGoogleGenAI.CATEGORY_MAPPING
    assert "BLOCK_NONE" in ProviderGoogleGenAI.THRESHOLD_MAPPING


@patch("astrbot.core.provider.sources.gemini_source.genai")
def test_gemini_construction_no_proxy(mock_genai):
    provider = ProviderGoogleGenAI(
        provider_config={"key": ["test-key"], "model": "gemini-2.0-flash"},
        provider_settings={},
    )
    assert provider.get_model() == "gemini-2.0-flash"
    assert provider.chosen_api_key == "test-key"
    mock_genai.Client.assert_called_once()


def test_gemini_empty_output_raises_error():
    llm_response = LLMResponse(role="assistant")
    with pytest.raises(EmptyModelOutputError):
        ProviderGoogleGenAI._ensure_usable_response(
            llm_response,
            response_id="resp_empty",
            finish_reason="STOP",
        )


def test_gemini_reasoning_only_output_is_allowed():
    llm_response = LLMResponse(
        role="assistant",
        reasoning_content="chain of thought placeholder",
    )
    ProviderGoogleGenAI._ensure_usable_response(
        llm_response,
        response_id="resp_reasoning",
        finish_reason="STOP",
    )
