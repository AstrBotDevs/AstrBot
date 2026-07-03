import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources.mimo_api_common import (
    MiMoAPIError,
    build_headers,
    prepare_audio_input,
)
from astrbot.core.provider.sources.mimo_stt_api_source import ProviderMiMoSTTAPI
from astrbot.core.provider.sources.mimo_tts_api_source import ProviderMiMoTTSAPI

MIMO_STT_TEST_AUDIO_DATA_URL = "data:audio/wav;base64,ZmFrZQ=="


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


def test_mimo_tts_user_prompt_returns_seed_text():
    provider = _make_tts_provider()
    try:
        assert provider._build_user_prompt() == "seed text"
    finally:
        asyncio.run(provider.terminate())


def test_mimo_tts_assistant_content_prefixes_style_and_dialect():
    provider = _make_tts_provider(
        {
            "mimo-tts-style-prompt": "开心",
            "mimo-tts-dialect": "四川话",
            "mimo-tts-seed-text": "You are chatting with a close friend.",
        }
    )
    try:
        payload = provider._build_payload("hello")
        assert payload["messages"][0] == {
            "role": "user",
            "content": "You are chatting with a close friend.",
        }
        assert payload["messages"][1]["content"] == "<style>开心 四川话</style>hello"
    finally:
        asyncio.run(provider.terminate())


def test_mimo_tts_payload_omits_user_message_without_seed_text():
    provider = _make_tts_provider(
        {
            "mimo-tts-seed-text": "",
            "mimo-tts-style-prompt": "开心",
        }
    )
    try:
        payload = provider._build_payload("hello")
        assert payload["messages"] == [
            {
                "role": "assistant",
                "content": "<style>开心</style>hello",
            }
        ]
    finally:
        asyncio.run(provider.terminate())


def test_mimo_tts_singing_style_uses_single_style_tag():
    provider = _make_tts_provider(
        {
            "mimo-tts-style-prompt": "唱歌 开心",
            "mimo-tts-dialect": "粤语",
        }
    )
    try:
        payload = provider._build_payload("歌词")
        assert payload["messages"][1]["content"] == "<style>唱歌</style>歌词"
    finally:
        asyncio.run(provider.terminate())


def test_mimo_tts_plain_text_stays_in_assistant_message_when_no_style():
    provider = _make_tts_provider(
        {
            "mimo-tts-seed-text": "",
        }
    )
    try:
        payload = provider._build_payload("hello")
        assert payload["messages"] == [
            {
                "role": "assistant",
                "content": "hello",
            }
        ]
    finally:
        asyncio.run(provider.terminate())


def test_mimo_tts_seed_text_is_not_prepended_to_assistant_content():
    provider = _make_tts_provider(
        {
            "mimo-tts-style-prompt": "开心",
            "mimo-tts-seed-text": "reference text",
        }
    )
    try:
        payload = provider._build_payload("明天就是周五了")
        assert payload["messages"][0]["content"] == "reference text"
        assert payload["messages"][1]["content"] == "<style>开心</style>明天就是周五了"
        assert "reference text" not in payload["messages"][1]["content"]
    finally:
        asyncio.run(provider.terminate())


def test_mimo_tts_voicedesign_model_omits_voice_param():
    """voice design 模型不应包含 audio.voice 参数"""
    provider = _make_tts_provider(
        {
            "model": "mimo-v2.5-tts-voicedesign",
            "mimo-tts-seed-text": "",
        }
    )
    try:
        payload = provider._build_payload("hello")
        assert "voice" not in payload["audio"]
        assert payload["audio"]["format"] == "wav"
    finally:
        asyncio.run(provider.terminate())


def test_mimo_tts_regular_model_includes_voice_param():
    """普通 TTS 模型应包含 audio.voice 参数"""
    provider = _make_tts_provider(
        {
            "model": "mimo-v2.5-tts",
            "mimo-tts-voice": "custom_voice",
            "mimo-tts-seed-text": "",
        }
    )
    try:
        payload = provider._build_payload("hello")
        assert payload["audio"]["voice"] == "custom_voice"
        assert payload["audio"]["format"] == "wav"
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
async def test_mimo_stt_payload_includes_audio_only(monkeypatch):
    provider = _make_stt_provider(
        {
            "mimo-stt-system-prompt": "system prompt",
            "mimo-stt-user-prompt": "user prompt",
        }
    )

    captured: dict = {}

    async def fake_prepare_audio_input(_audio_source: str):
        return MIMO_STT_TEST_AUDIO_DATA_URL, []

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
    assert captured["json"]["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": MIMO_STT_TEST_AUDIO_DATA_URL,
                    },
                },
            ],
        },
    ]


@pytest.mark.asyncio
async def test_mimo_stt_prepare_audio_input_returns_data_url(monkeypatch):
    class _ResolvedAudio:
        base64_data = "ZmFrZQ=="
        mime_type = "audio/wav"
        format = "wav"

        def to_data_url(self):
            return MIMO_STT_TEST_AUDIO_DATA_URL

    class _Resolver:
        def __init__(self, audio_source, **kwargs):
            assert audio_source == "/tmp/test.wav"
            assert kwargs == {
                "media_type": "audio",
                "default_suffix": ".wav",
            }

        async def to_base64_data(self, **kwargs):
            assert kwargs == {
                "strict": True,
                "target_format": "wav",
            }
            return _ResolvedAudio()

    monkeypatch.setattr(
        "astrbot.core.provider.sources.mimo_api_common.MediaResolver",
        _Resolver,
    )

    audio_data, cleanup_paths = await prepare_audio_input("/tmp/test.wav")

    assert audio_data == MIMO_STT_TEST_AUDIO_DATA_URL
    assert cleanup_paths == []


@pytest.mark.asyncio
async def test_mimo_stt_get_text_uses_reasoning_content(monkeypatch):
    provider = _make_stt_provider()

    async def fake_prepare_audio_input(_audio_source: str):
        return MIMO_STT_TEST_AUDIO_DATA_URL, []

    class _Response:
        status_code = 200
        text = '{"choices":[{"message":{"content":"","reasoning_content":"转写结果"}}]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {"message": {"content": "", "reasoning_content": "转写结果"}}
                ]
            }

    monkeypatch.setattr(
        "astrbot.core.provider.sources.mimo_stt_api_source.prepare_audio_input",
        fake_prepare_audio_input,
    )
    provider.client = SimpleNamespace(post=_fake_post(_Response()))

    assert await provider.get_text("/tmp/test.wav") == "转写结果"


@pytest.mark.asyncio
async def test_mimo_stt_get_text_handles_empty_choices(monkeypatch):
    provider = _make_stt_provider()

    async def fake_prepare_audio_input(_audio_source: str):
        return MIMO_STT_TEST_AUDIO_DATA_URL, []

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


@pytest.mark.asyncio
async def test_mimo_stt_get_text_handles_null_message(monkeypatch):
    provider = _make_stt_provider()

    async def fake_prepare_audio_input(_audio_source: str):
        return MIMO_STT_TEST_AUDIO_DATA_URL, []

    class _Response:
        status_code = 200
        text = '{"choices":[{"message":null}]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": None}]}

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
