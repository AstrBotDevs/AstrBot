"""Smoke tests for ProviderGoogleGenAI."""
import pytest
from unittest.mock import patch, MagicMock

from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.gemini_source import (
    ProviderGoogleGenAI,
    SuppressNonTextPartsWarning,
)


def test_gemini_import():
    assert ProviderGoogleGenAI is not None


def test_suppress_non_text_parts_warning_filter():
    flt = SuppressNonTextPartsWarning()
    record = MagicMock()
    record.getMessage.return_value = "there are non-text parts in the response"
    assert flt.filter(record) is False

    record.getMessage.return_value = "some other warning"
    assert flt.filter(record) is True


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
