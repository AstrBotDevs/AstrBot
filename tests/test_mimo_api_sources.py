import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources.mimo_api_common import MiMoAPIError, build_headers
from astrbot.core.provider.sources.mimo_stt_api_source import ProviderMiMoSTTAPI
from astrbot.core.provider.sources.mimo_tts_api_source import ProviderMiMoTTSAPI


def _make_tts_provider(overrides: dict | None = None) -> ProviderMiMoTTSAPI:
    provider_config = {
        "id": "test-mimo-tts",
        "type": "mimo_tts_api",
        "model": "mimo-v2-tts",
        "api_key": "test-key",
        "mimo-tts-voice": "mimo_default",
        "mimo-tts-format": "wav",
        "mimo-tts-seed-text": "seed text",
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderMiMoTTSAPI(provider_config=provider_config, provider_settings={})


def _make_stt_provider(overrides: dict | None = None) -> ProviderMiMoSTTAPI:
    provider_config = {
        "id": "test-mimo-stt",
        "type": "mimo_stt_api",
        "model": "mimo-v2-omni",
        "api_key": "test-key",
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderMiMoSTTAPI(provider_config=provider_config, provider_settings={})


def test_mimo_tts_prompt_returns_seed_text_when_no_style_or_dialect():
    provider = _make_tts_provider()
    try:
        assert provider._build_user_prompt() == "seed text"
    finally:
        asyncio.run(provider.terminate())


def test_mimo_tts_payload_includes_dialect_and_style_prompt():
    provider = _make_tts_provider(
        {
            "mimo-tts-style-prompt": "Please sound cheerful and lively.",
            "mimo-tts-dialect": "Sichuan dialect",
            "mimo-tts-seed-text": "You are chatting with a close friend.",
        }
    )
    try:
        payload = provider._build_payload("hello")
        assert payload["messages"][0]["content"] == (
            "Please sound cheerful and lively. "
            "Please use Sichuan dialect when speaking. "
            "You are chatting with a close friend."
        )
    finally:
        asyncio.run(provider.terminate())


def test_mimo_headers_use_single_authorization_method():
    assert build_headers("test-key") == {
        "Content-Type": "application/json",
        "Authorization": "Bearer test-key",
    }


@pytest.mark.asyncio
async def test_mimo_tts_get_audio_handles_empty_choices():
    provider = _make_tts_provider()

    class _Response:
        status_code = 200
        text = '{"choices":[]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": []}

    provider.client = SimpleNamespace(post=_fake_post(_Response()))

    with pytest.raises(MiMoAPIError, match="returned no audio payload"):
        await provider.get_audio("hello")


@pytest.mark.asyncio
async def test_mimo_stt_payload_includes_audio_and_prompt(monkeypatch):
    provider = _make_stt_provider(
        {
            "mimo-stt-system-prompt": "system prompt",
            "mimo-stt-user-prompt": "user prompt",
        }
    )

    captured: dict = {}

    async def fake_prepare_audio_input(_audio_source: str):
        return "ZmFrZQ==", []

    class _Response:
        status_code = 200
        text = '{"choices":[{"message":{"content":"transcribed text"}}]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "transcribed text"}}]}

    async def fake_post(_url, headers=None, json=None):
        captured["headers"] = headers
        captured["json"] = json
        return _Response()

    monkeypatch.setattr(
        "astrbot.core.provider.sources.mimo_stt_api_source.prepare_audio_input",
        fake_prepare_audio_input,
    )
    provider.client = SimpleNamespace(post=fake_post)

    result = await provider.get_text("/tmp/test.wav")

    assert result == "transcribed text"
    assert captured["json"]["messages"][0]["content"] == "system prompt"
    assert captured["json"]["messages"][1]["content"][0]["type"] == "input_audio"
    assert captured["json"]["messages"][1]["content"][0]["input_audio"]["data"] == "ZmFrZQ=="
    assert captured["json"]["messages"][1]["content"][1]["text"] == "user prompt"


@pytest.mark.asyncio
async def test_mimo_stt_get_text_handles_empty_choices(monkeypatch):
    provider = _make_stt_provider()

    async def fake_prepare_audio_input(_audio_source: str):
        return "ZmFrZQ==", []

    class _Response:
        status_code = 200
        text = '{"choices":[]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": []}

    monkeypatch.setattr(
        "astrbot.core.provider.sources.mimo_stt_api_source.prepare_audio_input",
        fake_prepare_audio_input,
    )
    provider.client = SimpleNamespace(post=_fake_post(_Response()))

    with pytest.raises(MiMoAPIError, match="returned empty transcription"):
        await provider.get_text("/tmp/test.wav")


def _fake_post(response):
    async def _post(*_args, **_kwargs):
        return response

    return _post
