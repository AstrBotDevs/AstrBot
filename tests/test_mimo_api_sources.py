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
        "mimo-tts-voiceclone-audio": "",
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


def test_mimo_tts_build_payload_voice_value_override_takes_precedence():
    """voice_value 显式传入时应覆盖 self.voice (用于 voiceclone data URL)"""
    provider = _make_tts_provider(
        {
            "model": "mimo-v2.5-tts-voiceclone",
            "mimo-tts-voice": "mimo_default",
            "mimo-tts-seed-text": "",
        }
    )
    try:
        payload = provider._build_payload(
            "hello", voice_value=MIMO_STT_TEST_AUDIO_DATA_URL
        )
        assert payload["audio"]["voice"] == MIMO_STT_TEST_AUDIO_DATA_URL
    finally:
        asyncio.run(provider.terminate())


def test_mimo_tts_is_voiceclone_model_detection():
    provider = _make_tts_provider({"model": "mimo-v2.5-tts-voiceclone"})
    try:
        assert provider._is_voiceclone_model() is True
    finally:
        asyncio.run(provider.terminate())

    provider2 = _make_tts_provider({"model": "mimo-v2.5-tts"})
    try:
        assert provider2._is_voiceclone_model() is False
    finally:
        asyncio.run(provider2.terminate())


@pytest.mark.asyncio
async def test_mimo_tts_voiceclone_without_audio_raises_clear_error():
    """选用 voiceclone 模型但未配置参考音频时应给出清晰报错，而不是悄悄发出错误请求"""
    provider = _make_tts_provider(
        {
            "model": "mimo-v2.5-tts-voiceclone",
            "mimo-tts-voiceclone-audio": "",
        }
    )
    try:
        with pytest.raises(MiMoAPIError, match="mimo-tts-voiceclone-audio"):
            await provider.get_audio("hello")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_mimo_tts_voiceclone_sends_audio_data_url_as_voice(monkeypatch):
    """voiceclone 模型应将参考音频转换的 data URL 填入 audio.voice 字段"""
    provider = _make_tts_provider(
        {
            "model": "mimo-v2.5-tts-voiceclone",
            "mimo-tts-voiceclone-audio": "/tmp/reference_voice.mp3",
            "mimo-tts-voice": "mimo_default",  # 应被忽略
            "mimo-tts-seed-text": "",
        }
    )

    call_count = {"n": 0}

    async def fake_prepare_audio_input(audio_source: str, **kwargs):
        call_count["n"] += 1
        assert audio_source == "/tmp/reference_voice.mp3"
        assert kwargs == {"target_format": None, "preserve_mp3": True}
        return MIMO_STT_TEST_AUDIO_DATA_URL, []

    monkeypatch.setattr(
        "astrbot.core.provider.sources.mimo_tts_api_source.prepare_audio_input",
        fake_prepare_audio_input,
    )

    captured: dict = {}

    class _Response:
        status_code = 200
        text = '{"choices":[{"message":{"audio":{"data":"ZmFrZQ=="}}}]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"audio": {"data": "ZmFrZQ=="}}}]}

    async def fake_post(_url, headers=None, json=None):
        captured["json"] = json
        return _Response()

    async def fake_aclose():
        return None

    provider.client = SimpleNamespace(post=fake_post, aclose=fake_aclose)

    try:
        output_path = await provider.get_audio("hello")
        assert captured["json"]["audio"]["voice"] == MIMO_STT_TEST_AUDIO_DATA_URL
        assert output_path.endswith(".wav")
        assert call_count["n"] == 1

        # 第二次调用同一来源的音频应使用缓存，不应重复转换
        await provider.get_audio("hello again")
        assert call_count["n"] == 1
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_mimo_tts_voiceclone_cache_refreshes_on_source_change(monkeypatch):
    """更换参考音频来源后应重新转换，而不是继续复用旧的缓存"""
    provider = _make_tts_provider(
        {
            "model": "mimo-v2.5-tts-voiceclone",
            "mimo-tts-voiceclone-audio": "/tmp/voice_a.mp3",
            "mimo-tts-seed-text": "",
        }
    )

    seen_sources: list[str] = []

    async def fake_prepare_audio_input(audio_source: str, **kwargs):
        seen_sources.append(audio_source)
        return f"data:audio/mpeg;base64,{audio_source}", []

    monkeypatch.setattr(
        "astrbot.core.provider.sources.mimo_tts_api_source.prepare_audio_input",
        fake_prepare_audio_input,
    )

    try:
        first_voice = await provider._resolve_voiceclone_voice()
        assert first_voice == "data:audio/mpeg;base64,/tmp/voice_a.mp3"

        provider.voiceclone_audio_source = "/tmp/voice_b.mp3"
        second_voice = await provider._resolve_voiceclone_voice()
        assert second_voice == "data:audio/mpeg;base64,/tmp/voice_b.mp3"
        assert seen_sources == ["/tmp/voice_a.mp3", "/tmp/voice_b.mp3"]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_mimo_tts_voiceclone_preserves_mp3_instead_of_forcing_wav(monkeypatch):
    """voiceclone 应保留原始 mp3 而不强制转 wav,避免体积不必要地膨胀"""
    provider = _make_tts_provider(
        {
            "model": "mimo-v2.5-tts-voiceclone",
            "mimo-tts-voiceclone-audio": "/tmp/reference_voice.mp3",
            "mimo-tts-seed-text": "",
        }
    )

    captured_kwargs: dict = {}

    async def fake_prepare_audio_input(audio_source: str, **kwargs):
        captured_kwargs.update(kwargs)
        return "data:audio/mp3;base64,ZmFrZQ==", []

    monkeypatch.setattr(
        "astrbot.core.provider.sources.mimo_tts_api_source.prepare_audio_input",
        fake_prepare_audio_input,
    )

    try:
        voice = await provider._resolve_voiceclone_voice()
        assert voice == "data:audio/mp3;base64,ZmFrZQ=="
        assert captured_kwargs == {"target_format": None, "preserve_mp3": True}
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_mimo_tts_voiceclone_concurrent_calls_convert_audio_once(monkeypatch):
    """并发调用 get_audio 时，参考音频只应被转换一次，不应出现重复转换或临时文件泄漏"""
    provider = _make_tts_provider(
        {
            "model": "mimo-v2.5-tts-voiceclone",
            "mimo-tts-voiceclone-audio": "/tmp/reference_voice.mp3",
            "mimo-tts-seed-text": "",
        }
    )

    call_count = {"n": 0}

    async def fake_prepare_audio_input(audio_source: str, **kwargs):
        call_count["n"] += 1
        # 模拟较慢的转码过程，放大并发窗口
        await asyncio.sleep(0.05)
        return MIMO_STT_TEST_AUDIO_DATA_URL, []

    monkeypatch.setattr(
        "astrbot.core.provider.sources.mimo_tts_api_source.prepare_audio_input",
        fake_prepare_audio_input,
    )

    try:
        results = await asyncio.gather(
            *[provider._resolve_voiceclone_voice() for _ in range(5)]
        )
        assert results == [MIMO_STT_TEST_AUDIO_DATA_URL] * 5
        assert call_count["n"] == 1
    finally:
        await provider.terminate()


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
                "preserve_mp3": False,
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
