import base64

import pytest
from google.genai import types

from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI


class _ConversationOnlyGeminiProvider(ProviderGoogleGenAI):
    def _init_client(self) -> None:
        self.client = None


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


def _make_gemini_provider_for_conversation():
    return _ConversationOnlyGeminiProvider(
        {
            "key": ["test-key"],
            "model": "gemini-test",
            "gm_native_coderunner": False,
            "gm_native_search": False,
        },
        {},
    )


def _assistant_tool_call_message(content):
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_pull_request_files",
                    "arguments": '{"owner":"AstrBotDevs","repo":"AstrBot","pull_number":8742}',
                },
            },
        ],
    }


def _first_model_parts(gemini_contents):
    model_content = next(
        content
        for content in gemini_contents
        if isinstance(content, types.ModelContent)
    )
    return model_content.parts or []


def test_prepare_conversation_keeps_assistant_text_and_tool_calls():
    provider = _make_gemini_provider_for_conversation()
    payloads = {
        "messages": [
            {"role": "user", "content": "summarize this PR"},
            _assistant_tool_call_message("I will inspect the changed files first."),
        ]
    }

    parts = _first_model_parts(provider._prepare_conversation(payloads))

    assert any(part.text == "I will inspect the changed files first." for part in parts)
    assert [
        part.function_call.name
        for part in parts
        if getattr(part, "function_call", None)
    ] == ["get_pull_request_files"]


def test_prepare_conversation_keeps_assistant_only_tool_calls_without_placeholder():
    provider = _make_gemini_provider_for_conversation()
    payloads = {
        "messages": [
            {"role": "user", "content": "summarize this PR"},
            _assistant_tool_call_message(None),
        ]
    }

    parts = _first_model_parts(provider._prepare_conversation(payloads))

    assert not any(part.text for part in parts)
    assert [
        part.function_call.name
        for part in parts
        if getattr(part, "function_call", None)
    ] == ["get_pull_request_files"]


def test_prepare_conversation_keeps_assistant_list_content_and_tool_calls():
    provider = _make_gemini_provider_for_conversation()
    payloads = {
        "messages": [
            {"role": "user", "content": "summarize this PR"},
            _assistant_tool_call_message(
                [
                    {
                        "type": "think",
                        "encrypted": base64.b64encode(b"signature").decode("utf-8"),
                    },
                    {"type": "text", "text": "I will inspect the changed files first."},
                ]
            ),
        ]
    }

    parts = _first_model_parts(provider._prepare_conversation(payloads))

    assert any(part.text == "I will inspect the changed files first." for part in parts)
    assert [
        part.function_call.name
        for part in parts
        if getattr(part, "function_call", None)
    ] == ["get_pull_request_files"]


def test_prepare_conversation_ignores_null_tool_calls():
    provider = _make_gemini_provider_for_conversation()
    payloads = {
        "messages": [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "hello back",
                "tool_calls": None,
            },
        ]
    }

    parts = _first_model_parts(provider._prepare_conversation(payloads))

    assert [part.text for part in parts] == ["hello back"]
    assert not any(getattr(part, "function_call", None) for part in parts)
