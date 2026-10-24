import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources.minimax_stt_api_source import (
    MiniMaxSTTAPIError,
    ProviderMiniMaxSTTAPI,
)


def _make_provider(overrides: dict | None = None) -> ProviderMiniMaxSTTAPI:
    provider_config = {
        "id": "test-minimax-stt",
        "type": "minimax_stt_api",
        "api_key": "test-key",
        "minimax-stt-language": "zh",
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderMiniMaxSTTAPI(provider_config, provider_settings={})


def test_minimax_stt_defaults():
    provider = _make_provider()
    try:
        assert provider.model_name == "asr-1.0"
        assert provider.api_base == "https://api.minimax.cn/v1/speech_to_text"
    finally:
        asyncio.run(provider.terminate())


@pytest.mark.asyncio
async def test_minimax_stt_uploads_audio_as_multipart(tmp_path: Path):
    provider = _make_provider(
        {
            "custom_headers": {
                "X-Gateway": "edge",
                "Authorization": "overridden",
                "language": "en",
            },
        }
    )
    audio_path = tmp_path / "voice.ogg"
    audio_path.write_bytes(b"OggSfake-audio")
    captured: dict = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "transcribed text"}

    async def fake_post(url, *, headers, data, files):
        captured.update(url=url, headers=headers, data=data, files=files)
        return Response()

    await provider.client.aclose()
    provider.client = SimpleNamespace(post=fake_post, aclose=lambda: None)

    assert await provider.get_text(str(audio_path)) == "transcribed text"
    assert captured["url"] == "https://api.minimax.cn/v1/speech_to_text"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["headers"]["language"] == "zh"
    assert captured["headers"]["X-Gateway"] == "edge"
    assert captured["data"] == {"model": "asr-1.0", "response_format": "json"}
    assert captured["files"]["file"][0] == "voice.ogg"
    assert captured["files"]["file"][2] == "audio/ogg"


@pytest.mark.asyncio
async def test_minimax_stt_returns_empty_text_for_silence(tmp_path: Path):
    provider = _make_provider()
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"RIFFfake-audio")

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"text": ""}

    async def fake_post(*_args, **_kwargs):
        return Response()

    await provider.client.aclose()
    provider.client = SimpleNamespace(post=fake_post, aclose=lambda: None)

    assert await provider.get_text(str(audio_path)) == ""


@pytest.mark.asyncio
async def test_minimax_stt_rejects_missing_transcription(tmp_path: Path):
    provider = _make_provider()
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"RIFFfake-audio")

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    async def fake_post(*_args, **_kwargs):
        return Response()

    await provider.client.aclose()
    provider.client = SimpleNamespace(post=fake_post, aclose=lambda: None)

    with pytest.raises(MiniMaxSTTAPIError, match="invalid transcription"):
        await provider.get_text(str(audio_path))


@pytest.mark.asyncio
async def test_minimax_stt_does_not_convert_non_silk_tencent_audio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_provider()

    async def fake_download(_url: str, path: str):
        Path(path).write_bytes(b"RIFFfake-audio")

    async def fail_conversion(*_args, **_kwargs):
        raise AssertionError("non-SILK Tencent audio must not be converted")

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "transcribed text"}

    async def fake_post(*_args, **_kwargs):
        return Response()

    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_stt_api_source.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_stt_api_source.download_file",
        fake_download,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_stt_api_source.tencent_silk_to_wav",
        fail_conversion,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_stt_api_source.convert_to_pcm_wav",
        fail_conversion,
    )
    await provider.client.aclose()
    provider.client = SimpleNamespace(post=fake_post, aclose=lambda: None)

    assert (
        await provider.get_text("https://multimedia.nt.qq.com.cn/download/record")
        == "transcribed text"
    )
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_minimax_stt_cleans_downloaded_audio_when_conversion_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_provider()

    async def fake_download(_url: str, path: str):
        Path(path).write_bytes(b"#!SILK_V3")

    async def fail_conversion(*_args, **_kwargs):
        raise RuntimeError("conversion failed")

    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_stt_api_source.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_stt_api_source.download_file",
        fake_download,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_stt_api_source.tencent_silk_to_wav",
        fail_conversion,
    )

    try:
        with pytest.raises(RuntimeError, match="conversion failed"):
            await provider.get_text("https://multimedia.nt.qq.com.cn/download/record")
        assert not list(tmp_path.iterdir())
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_minimax_stt_cleans_partial_download_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_provider()

    async def partial_download(_url: str, path: str):
        Path(path).write_bytes(b"partial")
        raise RuntimeError("download failed")

    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_stt_api_source.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_stt_api_source.download_file",
        partial_download,
    )

    try:
        with pytest.raises(RuntimeError, match="download failed"):
            await provider.get_text("https://example.com/audio.wav")
        assert not list(tmp_path.iterdir())
    finally:
        await provider.terminate()
