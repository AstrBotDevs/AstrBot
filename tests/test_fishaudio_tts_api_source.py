"""Unit tests for FishAudio TTS audio format and MP3 bitrate options."""

import logging
import os
from pathlib import Path
from unittest.mock import patch

import ormsgpack
import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.fishaudio_tts_api_source import (
    ProviderFishAudioTTSAPI,
)

VALID_REF_ID = "626bb6d3f3364c9cbc3aa6a67300a664"


def _make_provider(overrides: dict | None = None) -> ProviderFishAudioTTSAPI:
    config = {
        "id": "test_fishaudio_tts",
        "type": "fishaudio_tts_api",
        "provider": "fishaudio",
        "provider_type": "text_to_speech",
        "enable": True,
        "api_key": "test-key",
        "api_base": "https://api.fish.audio/v1",
        "model": "s2-pro",
        "fishaudio-tts-character": "可莉",
        "fishaudio-tts-reference-id": VALID_REF_ID,
        "timeout": "20",
        "proxy": "",
    }
    if overrides:
        config.update(overrides)
    return ProviderFishAudioTTSAPI(config, {})


class _FakeStreamResponse:
    def __init__(self, body: bytes, content_type: str, status_code: int = 200):
        self._body = body
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self):
        yield self._body

    async def aread(self):
        return self._body


@pytest.mark.asyncio
async def test_fishaudio_tts_defaults_to_wav_for_backward_compatibility():
    provider = _make_provider()
    assert provider.audio_format == "wav"
    assert provider.mp3_bitrate == 128

    req = await provider._generate_request("hello world")
    assert req.format == "wav"
    assert req.mp3_bitrate == 128
    assert req.reference_id == VALID_REF_ID


@pytest.mark.asyncio
async def test_fishaudio_tts_supports_mp3_and_bitrate_string_or_int(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    captured: dict = {}

    class _FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method: str, url: str, *, headers: dict, content: bytes):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = dict(headers)
            captured["payload"] = ormsgpack.unpackb(content)
            return _FakeStreamResponse(b"ID3fake-mp3-bytes", "audio/mpeg")

    provider = _make_provider(
        {
            "fishaudio-tts-format": "mp3",
            "fishaudio-tts-mp3-bitrate": "192",
        }
    )
    assert provider.audio_format == "mp3"
    assert provider.mp3_bitrate == 192

    with patch(
        "astrbot.core.provider.sources.fishaudio_tts_api_source.AsyncClient",
        _FakeAsyncClient,
    ):
        audio_path = await provider.get_audio("测试长语音")

    assert audio_path.endswith(".mp3")
    assert os.path.isfile(audio_path)
    assert Path(audio_path).read_bytes() == b"ID3fake-mp3-bytes"
    assert captured["payload"]["format"] == "mp3"
    assert captured["payload"]["mp3_bitrate"] == 192
    assert captured["payload"]["reference_id"] == VALID_REF_ID


@pytest.mark.asyncio
async def test_fishaudio_tts_invalid_format_and_bitrate_fall_back_safely():
    provider = _make_provider(
        {
            "fishaudio-tts-format": "flac",
            "fishaudio-tts-mp3-bitrate": "999",
        }
    )
    assert provider.audio_format == "wav"
    assert provider.mp3_bitrate == 128

    req = await provider._generate_request("fallback check")
    assert req.format == "wav"
    assert req.mp3_bitrate == 128


def test_fishaudio_tts_empty_bitrate_defaults_silently_and_bool_falls_back(caplog):
    with caplog.at_level(logging.WARNING, logger="astrbot"):
        p_empty = _make_provider({"fishaudio-tts-mp3-bitrate": ""})
        p_none = _make_provider({"fishaudio-tts-mp3-bitrate": None})
        p_ws = _make_provider({"fishaudio-tts-mp3-bitrate": "   "})
    assert p_empty.mp3_bitrate == 128
    assert p_none.mp3_bitrate == 128
    assert p_ws.mp3_bitrate == 128
    assert not any("码率" in r.message for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="astrbot"):
        p_bool = _make_provider({"fishaudio-tts-mp3-bitrate": True})
    assert p_bool.mp3_bitrate == 128
    assert any("码率" in r.message for r in caplog.records)


def test_fishaudio_tts_schema_exposes_format_and_bitrate_with_compat_defaults():
    provider_group = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]
    template = provider_group["config_template"]["FishAudio TTS(API)"]
    items = provider_group["items"]

    assert template["fishaudio-tts-format"] == "wav"
    assert template["fishaudio-tts-mp3-bitrate"] == "128"
    assert items["fishaudio-tts-format"]["options"] == ["wav", "mp3"]
    assert items["fishaudio-tts-mp3-bitrate"]["options"] == ["64", "128", "192"]
