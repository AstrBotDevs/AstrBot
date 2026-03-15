import pytest

from astrbot.core.provider.sources.minimax_source import ProviderMiniMax


def _make_minimax_provider(overrides: dict | None = None) -> ProviderMiniMax:
    provider_config = {
        "id": "test-minimax",
        "type": "minimax_chat_completion",
        "model": "MiniMax-M2.5",
        "key": ["test-key"],
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderMiniMax(
        provider_config=provider_config,
        provider_settings={},
    )


@pytest.mark.asyncio
async def test_minimax_provider_creation():
    provider = _make_minimax_provider()
    try:
        assert provider is not None
        assert provider.get_model() == "MiniMax-M2.5"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_minimax_provider_uses_default_base_url():
    provider = _make_minimax_provider()
    try:
        base_url = str(provider.client.base_url).rstrip("/")
        assert base_url == "https://api.minimax.io/v1"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_minimax_provider_respects_custom_base_url():
    custom_url = "https://api.minimaxi.com/v1"
    provider = _make_minimax_provider({"api_base": custom_url})
    try:
        assert str(provider.client.base_url).rstrip("/") == custom_url
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_minimax_provider_sets_model():
    provider = _make_minimax_provider({"model": "MiniMax-M2.5-highspeed"})
    try:
        assert provider.get_model() == "MiniMax-M2.5-highspeed"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_minimax_temperature_zero_is_corrected():
    provider = _make_minimax_provider()
    try:
        payloads = {
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0,
        }
        provider._finally_convert_payload(payloads)
        assert payloads["temperature"] == 1.0
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_minimax_temperature_negative_is_corrected():
    provider = _make_minimax_provider()
    try:
        payloads = {
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": -0.5,
        }
        provider._finally_convert_payload(payloads)
        assert payloads["temperature"] == 1.0
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_minimax_valid_temperature_is_kept():
    provider = _make_minimax_provider()
    try:
        payloads = {
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.7,
        }
        provider._finally_convert_payload(payloads)
        assert payloads["temperature"] == 0.7
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_minimax_response_format_is_removed():
    provider = _make_minimax_provider()
    try:
        payloads = {
            "messages": [{"role": "user", "content": "hello"}],
            "response_format": {"type": "json_object"},
        }
        provider._finally_convert_payload(payloads)
        assert "response_format" not in payloads
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_minimax_think_parts_are_converted():
    """MiniMax provider inherits think-part conversion from OpenAI base."""
    provider = _make_minimax_provider()
    try:
        payloads = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "think", "think": "reasoning step"},
                        {"type": "text", "text": "answer"},
                    ],
                }
            ]
        }
        provider._finally_convert_payload(payloads)
        msg = payloads["messages"][0]
        assert msg["content"] == [{"type": "text", "text": "answer"}]
        assert msg["reasoning_content"] == "reasoning step"
    finally:
        await provider.terminate()
