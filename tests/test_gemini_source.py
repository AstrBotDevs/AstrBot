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


def _make_text_part(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        thought=False,
        function_call=None,
        inline_data=None,
        thought_signature=None,
    )


def _make_function_call_part(
    name: str,
    args: dict,
    *,
    tool_call_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        text=None,
        thought=False,
        function_call=SimpleNamespace(
            name=name,
            args=args,
            id=tool_call_id,
        ),
        inline_data=None,
        thought_signature=None,
    )


@pytest.mark.asyncio
async def test_gemini_query_retries_empty_parts_response(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_provider()
    try:
        sleep_mock = AsyncMock()
        monkeypatch.setattr(
            "astrbot.core.provider.sources.gemini_source.asyncio.sleep",
            sleep_mock,
        )

        empty_result = _make_result([], "empty-response")
        success_result = _make_result(
            [_make_text_part("Recovered response")],
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


@pytest.mark.asyncio
async def test_gemini_query_retries_empty_parts_before_function_call(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_provider()
    try:
        sleep_mock = AsyncMock()
        monkeypatch.setattr(
            "astrbot.core.provider.sources.gemini_source.asyncio.sleep",
            sleep_mock,
        )

        empty_result = _make_result([], "empty-response")
        tool_call_result = _make_result(
            [
                _make_function_call_part(
                    "read_file",
                    {"path": "README.md"},
                    tool_call_id="call-readme",
                )
            ],
            "tool-call-response",
        )
        generate_content = AsyncMock(side_effect=[empty_result, tool_call_result])
        provider.client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content),
            aclose=AsyncMock(),
        )

        response = await provider._query(
            payloads={
                "messages": [{"role": "user", "content": "summarize the file"}],
                "model": "gemini-3-flash-preview",
            },
            tools=None,
        )

        assert generate_content.await_count == 2
        sleep_mock.assert_awaited_once()
        assert response.role == "tool"
        assert response.tools_call_name == ["read_file"]
        assert response.tools_call_args == [{"path": "README.md"}]
        assert response.tools_call_ids == ["call-readme"]
        assert response.id == "tool-call-response"
    finally:
        await provider.terminate()
