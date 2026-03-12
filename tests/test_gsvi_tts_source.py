from pathlib import Path

import pytest

from astrbot.core.provider.sources import gsvi_tts_source
from astrbot.core.provider.sources.gsvi_tts_source import ProviderGSVITTS


@pytest.mark.asyncio
async def test_resolve_infer_config_discovers_version_and_normalizes_default_emotion(
    monkeypatch,
):
    provider = ProviderGSVITTS(
        {
            "api_base": "https://gsv2p.example.com",
            "character": "Model A",
            "emotion": "default",
        },
        {},
    )

    async def fake_get_json(session, url):
        if url.endswith("/version"):
            return {"support_versions": ["v2", "v4"]}
        if url.endswith("/models/v2"):
            return {"models": {}}
        if url.endswith("/models/v4"):
            return {"models": {"Model A": {"中文": ["默认", "开心"]}}}
        raise AssertionError(url)

    monkeypatch.setattr(provider, "_get_json", fake_get_json)

    infer_config = await provider._resolve_infer_config(object())

    assert infer_config == {
        "version": "v4",
        "prompt_text_lang": "中文",
        "emotion": "默认",
    }


@pytest.mark.asyncio
async def test_get_audio_uses_infer_single_and_downloads_audio(monkeypatch, tmp_path: Path):
    provider = ProviderGSVITTS(
        {
            "api_base": "https://gsv2p.example.com",
            "character": "Model A",
            "emotion": "default",
        },
        {},
    )

    class FakeClientSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_resolve_infer_config(session):
        return {
            "version": "v4",
            "prompt_text_lang": "zh",
            "emotion": "默认",
        }

    async def fake_request_infer_audio(session, payload):
        assert payload["version"] == "v4"
        assert payload["model_name"] == "Model A"
        assert payload["prompt_text_lang"] == "zh"
        assert payload["emotion"] == "默认"
        assert payload["text"] == "你好"
        assert payload["text_lang"] == "中文"
        return "https://cdn.example.com/audio.wav"

    async def fake_download_binary(session, url, path):
        assert url == "https://cdn.example.com/audio.wav"
        Path(path).write_bytes(b"wav-bytes")

    monkeypatch.setattr(gsvi_tts_source, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(gsvi_tts_source.aiohttp, "ClientSession", FakeClientSession)
    monkeypatch.setattr(provider, "_resolve_infer_config", fake_resolve_infer_config)
    monkeypatch.setattr(provider, "_request_infer_audio", fake_request_infer_audio)
    monkeypatch.setattr(provider, "_download_binary", fake_download_binary)

    audio_path = await provider.get_audio("你好")

    assert Path(audio_path).read_bytes() == b"wav-bytes"
    assert str(tmp_path) in audio_path
