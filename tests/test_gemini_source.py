from types import SimpleNamespace

import httpx
import pytest
from google.genai import types

import astrbot.core.provider.sources.request_retry as request_retry
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI


@pytest.mark.asyncio
async def test_gemini_prepare_conversation_removes_leading_model_content():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = await provider._prepare_conversation(
        {
            "messages": [
                {"role": "assistant", "content": "stale assistant turn"},
                {"role": "user", "content": "current user turn"},
            ]
        }
    )

    assert len(contents) == 1
    assert isinstance(contents[0], types.UserContent)
    assert contents[0].parts is not None
    assert contents[0].parts[-1].text == "current user turn"


@pytest.mark.asyncio
async def test_gemini_prepare_conversation_keeps_normal_user_first_history():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = await provider._prepare_conversation(
        {
            "messages": [
                {"role": "user", "content": "first user turn"},
                {"role": "assistant", "content": "assistant turn"},
                {"role": "user", "content": "current user turn"},
            ]
        }
    )

    assert [type(content) for content in contents] == [
        types.UserContent,
        types.ModelContent,
        types.UserContent,
    ]
    assert contents[-1].parts is not None
    assert contents[-1].parts[-1].text == "current user turn"


@pytest.mark.asyncio
async def test_gemini_prepare_conversation_preserves_user_model_history():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = await provider._prepare_conversation(
        {
            "messages": [
                {"role": "user", "content": "user turn"},
                {"role": "assistant", "content": "assistant turn"},
            ]
        }
    )

    assert [type(content) for content in contents] == [
        types.UserContent,
        types.ModelContent,
    ]
    assert contents[-1].parts is not None
    assert contents[-1].parts[-1].text == "assistant turn"


@pytest.mark.asyncio
async def test_gemini_prepare_conversation_resolves_local_history_image(tmp_path):
    image_path = tmp_path / "history.webp"
    image_bytes = (
        b"RIFF\x16\x00\x00\x00WEBPVP8L\x0a\x00\x00\x00"
        b"/\x00\x00\x00\x10\x07\x10\x11\x11\x88\x88\xfe\x07"
    )
    image_path.write_bytes(image_bytes)
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = await provider._prepare_conversation(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "historical image"},
                        {
                            "type": "image_url",
                            "image_url": {"url": str(image_path)},
                        },
                    ],
                }
            ]
        }
    )

    assert contents[0].parts is not None
    image_part = contents[0].parts[1]
    assert image_part.inline_data is not None
    assert image_part.inline_data.mime_type == "image/webp"
    assert image_part.inline_data.data == image_bytes


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


def test_gemini_parallel_same_function_fallback_ids_are_unique():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    candidate = types.Candidate(
        content=types.Content(
            parts=[
                types.Part.from_function_call(name="weather", args={"city": "A"}),
                types.Part.from_function_call(name="weather", args={"city": "B"}),
            ]
        ),
        finish_reason=types.FinishReason.STOP,
    )
    llm_response = LLMResponse(role="assistant")

    provider._process_content_parts(candidate, llm_response)

    assert llm_response.tools_call_ids == ["weather", "weather__astrbot_2"]


def test_gemini_tool_responses_restore_function_name_from_unique_call_ids():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    payloads = {
        "messages": [
            {"role": "user", "content": "Check both cities"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "weather",
                        "type": "function",
                        "function": {
                            "name": "weather",
                            "arguments": '{"city":"A"}',
                        },
                    },
                    {
                        "id": "weather__astrbot_2",
                        "type": "function",
                        "function": {
                            "name": "weather",
                            "arguments": '{"city":"B"}',
                        },
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "weather", "content": "city A"},
            {
                "role": "tool",
                "tool_call_id": "weather__astrbot_2",
                "content": "city B",
            },
        ]
    }

    contents = provider._prepare_conversation(payloads)
    function_response_names = [
        part.function_response.name
        for content in contents
        for part in content.parts or []
        if part.function_response
    ]

    assert function_response_names == ["weather", "weather"]


@pytest.mark.asyncio
async def test_gemini_get_models_retries_transient_request_error(monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)

    class FakeModels:
        def __init__(self):
            self.calls = 0

        async def list(self):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError("temporary connection failure")
            return [
                SimpleNamespace(
                    name="models/gemini-a",
                    supported_actions=["generateContent"],
                ),
                SimpleNamespace(
                    name="models/gemini-b",
                    supported_actions=["embedContent"],
                ),
            ]

    models = FakeModels()
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.client = SimpleNamespace(models=models)

    assert await provider.get_models() == ["gemini-a"]
    assert models.calls == 2
