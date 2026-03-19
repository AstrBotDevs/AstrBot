from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.genai import types

from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI


def _make_provider(overrides: dict | None = None) -> ProviderGoogleGenAI:
    provider_config = {
        "id": "test-gemini",
        "type": "googlegenai_chat_completion",
        "model": "gemini-3-flash-preview",
        "key": ["test-key"],
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderGoogleGenAI(
        provider_config=provider_config,
        provider_settings={},
    )


def _make_result(parts: list | None, response_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=parts),
                finish_reason=types.FinishReason.STOP,
            )
        ],
        response_id=response_id,
        usage_metadata=None,
    )


@pytest.mark.asyncio
async def test_gemini_query_retries_empty_parts_response(monkeypatch: pytest.MonkeyPatch):
    provider = _make_provider()
    try:
        sleep_mock = AsyncMock()
        monkeypatch.setattr(
            "astrbot.core.provider.sources.gemini_source.asyncio.sleep",
            sleep_mock,
        )

        empty_result = _make_result([], "empty-response")
        success_result = _make_result(
            [
                SimpleNamespace(
                    text="Recovered response",
                    thought=False,
                    function_call=None,
                    inline_data=None,
                    thought_signature=None,
                )
            ],
            "success-response",
        )
        generate_content = AsyncMock(side_effect=[empty_result, success_result])
        provider.client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content),
            aclose=AsyncMock(),
        )

        response = await provider._query(
            payloads={
                "messages": [{"role": "user", "content": "hello"}],
                "model": "gemini-3-flash-preview",
            },
            tools=None,
        )

        assert generate_content.await_count == 2
        sleep_mock.assert_awaited_once()
        assert response.completion_text == "Recovered response"
        assert response.id == "success-response"
    finally:
        await provider.terminate()
