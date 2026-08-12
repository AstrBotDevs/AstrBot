import asyncio
from types import SimpleNamespace

from astrbot.core.provider.sources.deepseek_source import ProviderDeepSeek


def _make_provider(overrides: dict | None = None) -> ProviderDeepSeek:
    provider_config = {
        "id": "test-deepseek",
        "type": "deepseek_chat_completion",
        "model": "deepseek-v4-flash",
        "key": ["test-key"],
        "custom_extra_body": {},
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderDeepSeek(
        provider_config=provider_config,
        provider_settings={},
    )


def test_deepseek_thinking_mode_removes_tool_choice_from_payload_and_extra_body():
    provider = _make_provider(
        {
            "custom_extra_body": {
                "thinking": {"type": "enabled"},
                "tool_choice": "required",
            }
        }
    )
    try:
        payloads = {
            "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": "hello"}],
            "tool_choice": "required",
        }

        normalized_payloads, extra_body, _ = provider._prepare_request(payloads, None)

        assert "tool_choice" not in normalized_payloads
        assert "tool_choice" not in extra_body
        assert extra_body["thinking"]["type"] == "enabled"
    finally:
        asyncio.run(provider.terminate())


def test_deepseek_non_thinking_mode_keeps_tool_choice():
    provider = _make_provider(
        {
            "custom_extra_body": {
                "thinking": {"type": "disabled"},
            }
        }
    )
    try:
        payloads = {
            "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": "hello"}],
            "tool_choice": "required",
        }

        normalized_payloads, extra_body, _ = provider._prepare_request(payloads, None)

        assert normalized_payloads["tool_choice"] == "required"
        assert extra_body["thinking"]["type"] == "disabled"
    finally:
        asyncio.run(provider.terminate())


def test_deepseek_non_thinking_payload_does_not_inject_empty_reasoning_content():
    provider = ProviderDeepSeek.__new__(ProviderDeepSeek)
    provider.provider_config = {
        "custom_extra_body": {
            "thinking": {"type": "disabled"},
        }
    }
    provider.client = SimpleNamespace(base_url=SimpleNamespace(host="api.deepseek.com"))

    payloads = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "assistant", "content": "previous reply"}],
    }

    provider._finally_convert_payload(payloads)

    assert "reasoning_content" not in payloads["messages"][0]


def test_deepseek_thinking_payload_keeps_empty_reasoning_content_for_history():
    provider = ProviderDeepSeek.__new__(ProviderDeepSeek)
    provider.provider_config = {
        "custom_extra_body": {
            "thinking": {"type": "enabled"},
        }
    }
    provider.client = SimpleNamespace(base_url=SimpleNamespace(host="api.deepseek.com"))

    payloads = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "assistant", "content": "previous reply"}],
    }

    provider._finally_convert_payload(payloads)

    assert payloads["messages"][0]["reasoning_content"] == ""
