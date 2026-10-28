from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.register import provider_cls_map
from astrbot.core.provider.sources.minimax_stt_api_source import (
    ProviderMiniMaxSTTAPI,
)


def _make_provider(overrides: dict | None = None) -> ProviderMiniMaxSTTAPI:
    provider_config = {
        "id": "test-minimax-stt",
        "type": "minimax_stt_api",
        "model": "asr-1.0",
        "api_key": "test-key",
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderMiniMaxSTTAPI(provider_config=provider_config, provider_settings={})


@pytest.mark.asyncio
async def test_transcription_url_appends_path_suffix(tmp_path: Path):
    provider = _make_provider({"api_base": "https://api.minimaxi.com/v1"})
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"RIFF\x24\x08\x00\x00WAVEfmt ")

    captured: dict = {}

    class _Response:
        status_code = 200
        text = '{"text": "hello"}'

        def json(self):
            return {"text": "hello"}

    async def fake_post(url, **kwargs):
        captured["url"] = url
        return _Response()

    provider.client = SimpleNamespace(post=fake_post, aclose=None)

    await provider.get_text(str(audio_path))

    assert captured["url"] == "https://api.minimaxi.com/v1/speech_to_text"


@pytest.mark.asyncio
async def test_transcription_url_keeps_explicit_endpoint(tmp_path: Path):
    provider = _make_provider(
        {"api_base": "https://api.minimaxi.com/v1/speech_to_text"}
    )
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"RIFF\x24\x08\x00\x00WAVEfmt ")

    captured: dict = {}

    class _Response:
        status_code = 200
        text = '{"text": "hello"}'

        def json(self):
            return {"text": "hello"}

    async def fake_post(url, **kwargs):
        captured["url"] = url
        return _Response()

    provider.client = SimpleNamespace(post=fake_post, aclose=None)

    await provider.get_text(str(audio_path))

    assert captured["url"] == "https://api.minimaxi.com/v1/speech_to_text"


@pytest.mark.asyncio
async def test_get_text_returns_transcription(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    provider = _make_provider()
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"RIFF\x24\x08\x00\x00WAVEfmt ")

    captured: dict = {}

    class _Response:
        status_code = 200
        text = '{"text": "hello world", "duration": 1.5}'

        def json(self):
            return {"text": "hello world", "duration": 1.5}

    async def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["data"] = kwargs.get("data")
        captured["files"] = kwargs.get("files")
        return _Response()

    provider.client = SimpleNamespace(post=fake_post, aclose=None)

    result = await provider.get_text(str(audio_path))

    assert result == "hello world"
    assert captured["url"] == "https://api.minimaxi.com/v1/speech_to_text"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["data"]["model"] == "asr-1.0"
    assert captured["data"]["response_format"] == "json"
    assert captured["files"]["file"][0].endswith(".wav")
    assert captured["files"]["file"][1] == b"RIFF\x24\x08\x00\x00WAVEfmt "


@pytest.mark.asyncio
async def test_get_text_raises_on_api_error(tmp_path: Path):
    provider = _make_provider()
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"RIFF\x24\x08\x00\x00WAVEfmt ")

    class _Response:
        status_code = 401
        text = '{"type":"error","error":{"message":"login fail"}}'

    async def fake_post(url, **kwargs):
        return _Response()

    provider.client = SimpleNamespace(post=fake_post, aclose=None)

    with pytest.raises(Exception, match="HTTP 401"):
        await provider.get_text(str(audio_path))


@pytest.mark.asyncio
async def test_get_text_raises_on_empty_transcription(tmp_path: Path):
    provider = _make_provider()
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"RIFF\x24\x08\x00\x00WAVEfmt ")

    class _Response:
        status_code = 200
        text = '{"text": ""}'

        def json(self):
            return {"text": ""}

    async def fake_post(url, **kwargs):
        return _Response()

    provider.client = SimpleNamespace(post=fake_post, aclose=None)

    with pytest.raises(Exception, match="empty transcription"):
        await provider.get_text(str(audio_path))


def test_minimax_stt_template_is_registered_as_speech_to_text_provider():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    template = templates["MiniMax STT(API)"]

    assert template["type"] == "minimax_stt_api"
    assert template["provider_type"] == "speech_to_text"
    assert template["model"] == "asr-1.0"

    metadata = provider_cls_map["minimax_stt_api"]
    assert metadata.cls_type is ProviderMiniMaxSTTAPI
    assert metadata.provider_type.value == "speech_to_text"
