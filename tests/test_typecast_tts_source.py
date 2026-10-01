import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.provider.sources.typecast_tts_source import ProviderTypecastTTS


def _make_provider(**overrides) -> ProviderTypecastTTS:
    config = {
        "id": "test-typecast",
        "type": "typecast_tts",
        "api_key": "test-api-key",
        "typecast-voice-id": "tc_60e5426de8b95f1d3000d7b5",
        "model": "ssfm-v30",
        "language": "kor",
        "typecast-emotion-preset": "normal",
        "typecast-emotion-intensity": 1.0,
        "typecast-volume": 100,
        "typecast-pitch": 0,
        "typecast-tempo": 1.0,
        "timeout": 30,
    }
    config.update(overrides)
    return ProviderTypecastTTS(provider_config=config, provider_settings={})


@pytest.mark.asyncio
async def test_get_audio_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Successful API call saves WAV and returns path."""
    provider = _make_provider()

    monkeypatch.setattr(
        "astrbot.core.provider.sources.typecast_tts_source.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    fake_response = AsyncMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "audio/wav"}
    fake_response.aiter_bytes = lambda: _async_iter([b"RIFF", b"fake_wav_data"])

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.stream = MagicMock(return_value=_async_context_manager(fake_response))

    monkeypatch.setattr(
        "astrbot.core.provider.sources.typecast_tts_source.AsyncClient",
        lambda **kwargs: fake_client,
    )

    path = await provider.get_audio("Hello world")

    assert path.endswith(".wav")
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == b"RIFFfake_wav_data"


@pytest.mark.asyncio
async def test_get_audio_api_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """API error raises RuntimeError with detail message."""
    provider = _make_provider()

    monkeypatch.setattr(
        "astrbot.core.provider.sources.typecast_tts_source.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    fake_response = AsyncMock()
    fake_response.status_code = 401
    fake_response.headers = {"content-type": "application/json"}
    fake_response.aread = AsyncMock(return_value=b'{"detail": "Invalid API key"}')

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.stream = MagicMock(return_value=_async_context_manager(fake_response))

    monkeypatch.setattr(
        "astrbot.core.provider.sources.typecast_tts_source.AsyncClient",
        lambda **kwargs: fake_client,
    )

    with pytest.raises(RuntimeError, match="Invalid API key"):
        await provider.get_audio("Hello world")


@pytest.mark.asyncio
async def test_get_audio_request_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify the request body sent to Typecast API."""
    provider = _make_provider(
        **{
            "typecast-emotion-preset": "happy",
            "typecast-emotion-intensity": 1.5,
            "typecast-pitch": 3,
            "typecast-tempo": 1.2,
        }
    )

    monkeypatch.setattr(
        "astrbot.core.provider.sources.typecast_tts_source.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    captured_kwargs = {}

    fake_response = AsyncMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "audio/wav"}
    fake_response.aiter_bytes = lambda: _async_iter([b"fake_wav"])

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)

    def capture_stream(method, url, **kwargs):
        captured_kwargs.update(kwargs)
        return _async_context_manager(fake_response)

    fake_client.stream = capture_stream

    monkeypatch.setattr(
        "astrbot.core.provider.sources.typecast_tts_source.AsyncClient",
        lambda **kwargs: fake_client,
    )

    await provider.get_audio("Test text")

    body = captured_kwargs["json"]
    assert body["voice_id"] == "tc_60e5426de8b95f1d3000d7b5"
    assert body["text"] == "Test text"
    assert body["model"] == "ssfm-v30"
    assert body["language"] == "kor"
    assert body["prompt"]["emotion_type"] == "preset"
    assert body["prompt"]["emotion_preset"] == "happy"
    assert body["prompt"]["emotion_intensity"] == 1.5
    assert body["output"]["audio_pitch"] == 3
    assert body["output"]["audio_tempo"] == 1.2
    assert body["output"]["audio_format"] == "wav"
    assert body["output"]["volume"] == 100


def test_provider_config_defaults():
    """Default config values are applied correctly."""
    provider = ProviderTypecastTTS(
        provider_config={
            "id": "test-typecast",
            "type": "typecast_tts",
            "api_key": "test-api-key",
            "typecast-voice-id": "tc_60e5426de8b95f1d3000d7b5",
        },
        provider_settings={},
    )
    assert provider.voice_id == "tc_60e5426de8b95f1d3000d7b5"
    assert provider.model_name == "ssfm-v30"
    assert provider.language == "kor"
    assert provider.emotion_preset == "normal"
    assert provider.emotion_intensity == 1.0
    assert provider.volume == 100
    assert provider.pitch == 0
    assert provider.tempo == 1.0
    assert provider.timeout == 30


def test_provider_config_missing_api_key():
    """Missing api_key raises ValueError."""
    with pytest.raises(ValueError, match="api_key is required"):
        ProviderTypecastTTS(
            provider_config={
                "id": "test",
                "type": "typecast_tts",
                "typecast-voice-id": "tc_123",
            },
            provider_settings={},
        )


def test_provider_config_missing_voice_id():
    """Missing voice_id raises ValueError."""
    with pytest.raises(ValueError, match="typecast-voice-id is required"):
        ProviderTypecastTTS(
            provider_config={
                "id": "test",
                "type": "typecast_tts",
                "api_key": "test-key",
            },
            provider_settings={},
        )


@pytest.mark.asyncio
async def test_get_audio_empty_text():
    """Empty text raises ValueError."""
    provider = _make_provider()
    with pytest.raises(ValueError, match="text must not be empty"):
        await provider.get_audio("")


@pytest.mark.asyncio
async def test_get_audio_whitespace_text():
    """Whitespace-only text raises ValueError."""
    provider = _make_provider()
    with pytest.raises(ValueError, match="text must not be empty"):
        await provider.get_audio("   \n\t")


@pytest.mark.asyncio
async def test_get_audio_text_too_long():
    """Text exceeding 2000 chars raises ValueError."""
    provider = _make_provider()
    with pytest.raises(ValueError, match="exceeds maximum of 2000 characters"):
        await provider.get_audio("a" * 2001)


def test_provider_config_invalid_emotion_preset_falls_back():
    """Invalid emotion preset falls back to 'normal'."""
    provider = _make_provider(**{"typecast-emotion-preset": "invalid_emotion"})
    assert provider.emotion_preset == "normal"


@pytest.mark.asyncio
async def test_get_audio_passes_timeout_and_proxy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify timeout and proxy are passed to AsyncClient."""
    provider = _make_provider(timeout=10, proxy="http://localhost:8080")

    monkeypatch.setattr(
        "astrbot.core.provider.sources.typecast_tts_source.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    captured_client_kwargs = {}

    fake_response = AsyncMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "audio/wav"}
    fake_response.aiter_bytes = lambda: _async_iter([b"fake_wav"])

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.stream = MagicMock(return_value=_async_context_manager(fake_response))

    def capture_async_client(**kwargs):
        captured_client_kwargs.update(kwargs)
        return fake_client

    monkeypatch.setattr(
        "astrbot.core.provider.sources.typecast_tts_source.AsyncClient",
        capture_async_client,
    )

    await provider.get_audio("Test")

    assert captured_client_kwargs["timeout"] == 10
    assert captured_client_kwargs["proxy"] == "http://localhost:8080"


def test_provider_config_invalid_numbers_use_defaults():
    """Invalid numeric config values fall back to defaults."""
    provider = ProviderTypecastTTS(
        provider_config={
            "id": "test-typecast",
            "type": "typecast_tts",
            "api_key": "test-api-key",
            "typecast-voice-id": "tc_60e5426de8b95f1d3000d7b5",
            "typecast-emotion-intensity": "not-a-number",
            "typecast-volume": "not-a-number",
            "typecast-pitch": "not-a-number",
            "typecast-tempo": "not-a-number",
            "timeout": "not-a-number",
        },
        provider_settings={},
    )
    assert provider.emotion_intensity == 1.0
    assert provider.volume == 100
    assert provider.pitch == 0
    assert provider.tempo == 1.0
    assert provider.timeout == 30


# --- Test helpers ---

async def _async_iter(items):
    for item in items:
        yield item


class _async_context_manager:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        pass
