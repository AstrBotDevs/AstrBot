import pytest

from astrbot.core.config.default import ASTRBOT_USER_AGENT
from astrbot.core.exceptions import EmptyModelOutputError
import astrbot.core.provider.sources.gemini_source as gemini_source
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI


class _FakeGenAIClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._api_client = type(
            "FakeAPIClient",
            (),
            {"_http_options": kwargs["http_options"]},
        )()
        self.aio = type("FakeAioClient", (), {"_api_client": self._api_client})()


@pytest.mark.asyncio
async def test_gemini_provider_uses_astrbot_default_user_agent(monkeypatch):
    monkeypatch.setattr(gemini_source.genai, "Client", _FakeGenAIClient)

    provider = ProviderGoogleGenAI(
        provider_config={
            "id": "gemini-test",
            "type": "googlegenai_chat_completion",
            "model": "gemini-test",
            "key": ["test-key"],
            "api_base": "https://generativelanguage.googleapis.com/",
        },
        provider_settings={},
    )

    try:
        assert provider.custom_headers["user-agent"] == ASTRBOT_USER_AGENT
        assert provider.client._api_client._http_options.headers["user-agent"] == (
            ASTRBOT_USER_AGENT
        )
        assert provider._http_client.headers["user-agent"] == ASTRBOT_USER_AGENT
    finally:
        await provider.terminate()


def test_gemini_empty_output_raises_empty_model_output_error():
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
