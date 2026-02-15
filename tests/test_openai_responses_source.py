import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astrbot.core.agent.message import Message
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)


class _DummyError(Exception):
    def __init__(self, message: str, status_code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _provider() -> ProviderOpenAIResponses:
    return ProviderOpenAIResponses.__new__(ProviderOpenAIResponses)


def test_is_retryable_upstream_error_with_5xx_status():
    err = _DummyError("server error", status_code=502)

    assert _provider()._is_retryable_upstream_error(err)


def test_is_retryable_upstream_error_with_upstream_error_type():
    err = _DummyError(
        "bad gateway",
        status_code=400,
        body={"error": {"type": "upstream_error"}},
    )

    assert _provider()._is_retryable_upstream_error(err)


def test_is_retryable_upstream_error_returns_false_for_non_retryable_error():
    err = _DummyError(
        "invalid request",
        status_code=400,
        body={"error": {"type": "invalid_request_error"}},
    )

    assert not _provider()._is_retryable_upstream_error(err)


def test_build_responses_input_and_instructions_moves_system_messages():
    provider = _provider()
    provider.custom_headers = {}

    response_input, instructions = provider._build_responses_input_and_instructions(
        [
            {"role": "system", "content": "sys text"},
            {"role": "developer", "content": [{"type": "text", "text": "dev text"}]},
            {"role": "user", "content": "hello"},
        ]
    )

    assert instructions == "sys text\n\ndev text"
    assert all(
        item.get("role") not in {"system", "developer"} for item in response_input
    )
    assert any(item.get("role") == "user" for item in response_input)


def test_build_extra_headers_keeps_custom_headers_and_ignores_authorization():
    provider = _provider()
    provider.custom_headers = {
        "X-Test": "value",
        "Authorization": "Bearer should-not-pass",
    }

    headers = provider._build_extra_headers()

    assert "User-Agent" not in headers
    assert headers["X-Test"] == "value"
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_compact_context_uses_sdk_compact_api():
    provider = _provider()
    provider.provider_config = {"proxy": ""}
    provider.get_model = lambda: "gpt-5.3-codex"
    provider._ensure_message_to_dicts = lambda messages: [
        {"role": "user", "content": "hello"}
    ]
    provider._messages_to_response_input = lambda _: [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hello"}],
        }
    ]
    provider._build_extra_headers = lambda: {"X-Test": "1"}

    compact_mock = AsyncMock(
        return_value=SimpleNamespace(
            model_dump=lambda mode="json": {
                "output": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "output_text", "text": "compacted"}],
                    }
                ]
            }
        )
    )
    provider.client = SimpleNamespace(responses=SimpleNamespace(compact=compact_mock))

    result = await provider.compact_context([Message(role="user", content="hello")])

    compact_mock.assert_awaited_once_with(
        model="gpt-5.3-codex",
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ],
        extra_headers={"X-Test": "1"},
    )
    assert result


@pytest.mark.asyncio
async def test_compact_context_raises_when_compact_returns_empty_messages():
    provider = _provider()
    provider.provider_config = {"proxy": ""}
    provider.get_model = lambda: "gpt-5.3-codex"
    provider._ensure_message_to_dicts = lambda messages: [
        {"role": "user", "content": "hello"}
    ]
    provider._messages_to_response_input = lambda _: [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hello"}],
        }
    ]
    provider._build_extra_headers = lambda: {}

    compact_mock = AsyncMock(
        return_value=SimpleNamespace(model_dump=lambda mode="json": {"output": []})
    )
    provider.client = SimpleNamespace(responses=SimpleNamespace(compact=compact_mock))

    with pytest.raises(ValueError, match="empty context"):
        await provider.compact_context([Message(role="user", content="hello")])


def test_convert_tools_to_responses_does_not_force_strict_false():
    provider = _provider()
    provider.provider_config = {}

    response_tools = provider._convert_tools_to_responses(
        [
            {
                "type": "function",
                "function": {
                    "name": "demo",
                    "description": "desc",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
    )

    assert response_tools
    assert "strict" not in response_tools[0]


def test_convert_tools_to_responses_keeps_explicit_strict_setting():
    provider = _provider()
    provider.provider_config = {}

    response_tools = provider._convert_tools_to_responses(
        [
            {
                "type": "function",
                "function": {
                    "name": "demo",
                    "description": "desc",
                    "parameters": {"type": "object", "properties": {}},
                    "strict": True,
                },
            }
        ]
    )

    assert response_tools[0]["strict"] is True


def test_convert_tools_to_responses_supports_provider_default_strict():
    provider = _provider()
    provider.provider_config = {"responses_tool_strict": True}

    response_tools = provider._convert_tools_to_responses(
        [
            {
                "type": "function",
                "function": {
                    "name": "demo",
                    "description": "desc",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
    )

    assert response_tools[0]["strict"] is True
