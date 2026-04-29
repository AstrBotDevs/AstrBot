import httpx
import pytest

import astrbot.core.provider.sources.anthropic_source as anthropic_source
import astrbot.core.provider.sources.kimi_code_source as kimi_code_source
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse


class _FakeAsyncAnthropic:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def close(self):
        return None


def test_anthropic_provider_injects_custom_headers_into_http_client(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = anthropic_source.ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
            "custom_headers": {
                "User-Agent": "custom-agent/1.0",
                "X-Test-Header": 123,
            },
        },
        provider_settings={},
    )

    assert provider.custom_headers == {
        "User-Agent": "custom-agent/1.0",
        "X-Test-Header": "123",
    }
    assert isinstance(provider.client.kwargs["http_client"], httpx.AsyncClient)  # type: ignore[attr-defined]
    assert provider.client.kwargs["http_client"].headers["User-Agent"] == "custom-agent/1.0"  # type: ignore[attr-defined]
    assert provider.client.kwargs["http_client"].headers["X-Test-Header"] == "123"  # type: ignore[attr-defined]


def test_kimi_code_provider_sets_defaults_and_preserves_custom_headers(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = kimi_code_source.ProviderKimiCode(
        provider_config={
            "id": "kimi-code",
            "type": "kimi_code_chat_completion",
            "key": ["test-key"],
            "custom_headers": {"X-Trace-Id": "trace-1"},
        },
        provider_settings={},
    )

    assert provider.base_url == kimi_code_source.KIMI_CODE_API_BASE
    assert provider.get_model() == kimi_code_source.KIMI_CODE_DEFAULT_MODEL
    assert provider.custom_headers == {
        "User-Agent": kimi_code_source.KIMI_CODE_USER_AGENT,
        "X-Trace-Id": "trace-1",
    }
    assert provider.client.kwargs["http_client"].headers["User-Agent"] == (  # type: ignore[attr-defined]
        kimi_code_source.KIMI_CODE_USER_AGENT
    )
    assert provider.client.kwargs["http_client"].headers["X-Trace-Id"] == "trace-1"  # type: ignore[attr-defined]


def test_kimi_code_provider_restores_required_user_agent_when_blank(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = kimi_code_source.ProviderKimiCode(
        provider_config={
            "id": "kimi-code",
            "type": "kimi_code_chat_completion",
            "key": ["test-key"],
            "custom_headers": {"User-Agent": "   "},
        },
        provider_settings={},
    )

    assert provider.custom_headers == {
        "User-Agent": kimi_code_source.KIMI_CODE_USER_AGENT,
    }


def test_anthropic_empty_output_raises_empty_model_output_error():
    llm_response = LLMResponse(role="assistant")

    with pytest.raises(EmptyModelOutputError):
        anthropic_source.ProviderAnthropic._ensure_usable_response(
            llm_response,
            completion_id="msg_empty",
            stop_reason="end_turn",
        )


def _make_anthropic_provider_for_payload_tests() -> anthropic_source.ProviderAnthropic:
    return anthropic_source.ProviderAnthropic(
        provider_config={"model": "claude-test"},
        provider_settings={},
        use_api_key=False,
    )


def test_prepare_payload_merges_consecutive_tool_results_into_single_user_message():
    provider = _make_anthropic_provider_for_payload_tests()

    _, new_messages = provider._prepare_payload(
        [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Reading files"}],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call_00",
                        "function": {
                            "name": "astrbot_file_read_tool",
                            "arguments": '{"path": "/tmp/one.txt"}',
                        },
                    },
                    {
                        "type": "function",
                        "id": "call_01",
                        "function": {
                            "name": "astrbot_file_read_tool",
                            "arguments": '{"path": "/tmp/two.txt"}',
                        },
                    },
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_00",
                "content": "one",
            },
            {
                "role": "tool",
                "tool_call_id": "call_01",
                "content": "two",
            },
        ]
    )

    assert len(new_messages) == 2
    assert new_messages[1]["role"] == "user"
    assert new_messages[1]["content"] == [
        {"type": "tool_result", "tool_use_id": "call_00", "content": "one"},
        {"type": "tool_result", "tool_use_id": "call_01", "content": "two"},
    ]


def test_prepare_payload_keeps_single_tool_result_as_single_user_message():
    provider = _make_anthropic_provider_for_payload_tests()

    _, new_messages = provider._prepare_payload(
        [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Reading file"}],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call_00",
                        "function": {
                            "name": "astrbot_file_read_tool",
                            "arguments": '{"path": "/tmp/one.txt"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_00",
                "content": "one",
            },
        ]
    )

    assert len(new_messages) == 2
    assert new_messages[1] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "call_00", "content": "one"}
        ],
    }


def test_prepare_payload_does_not_merge_non_consecutive_tool_results():
    provider = _make_anthropic_provider_for_payload_tests()

    _, new_messages = provider._prepare_payload(
        [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "First tool"}],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call_00",
                        "function": {
                            "name": "astrbot_file_read_tool",
                            "arguments": '{"path": "/tmp/one.txt"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_00",
                "content": "one",
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Second tool"}],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call_01",
                        "function": {
                            "name": "astrbot_file_read_tool",
                            "arguments": '{"path": "/tmp/two.txt"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_01",
                "content": "two",
            },
        ]
    )

    assert new_messages == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "First tool"},
                {
                    "type": "tool_use",
                    "name": "astrbot_file_read_tool",
                    "input": {"path": "/tmp/one.txt"},
                    "id": "call_00",
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_00", "content": "one"}
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Second tool"},
                {
                    "type": "tool_use",
                    "name": "astrbot_file_read_tool",
                    "input": {"path": "/tmp/two.txt"},
                    "id": "call_01",
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_01", "content": "two"}
            ],
        },
    ]
