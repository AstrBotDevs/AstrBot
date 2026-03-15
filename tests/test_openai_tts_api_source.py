import asyncio
from pathlib import Path

import pytest

from astrbot.core.provider.sources import openai_tts_api_source
from astrbot.core.provider.sources.openai_tts_api_source import ProviderOpenAITTSAPI


class FakeStreamingResponse:
    def __init__(self, chunks: list[bytes], headers: dict[str, str] | None = None):
        self._chunks = chunks
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def iter_bytes(self, chunk_size: int = 1024):
        for chunk in self._chunks:
            yield chunk


class FakeStreamingSpeech:
    def __init__(self, response: FakeStreamingResponse):
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response: FakeStreamingResponse):
        self.audio = type(
            "FakeAudio",
            (),
            {
                "speech": type(
                    "FakeSpeech",
                    (),
                    {"with_streaming_response": FakeStreamingSpeech(response)},
                )()
            },
        )()
        self.closed = False

    async def close(self):
        self.closed = True


def make_provider(monkeypatch, response: FakeStreamingResponse) -> ProviderOpenAITTSAPI:
    fake_client = FakeClient(response)
    monkeypatch.setattr(openai_tts_api_source, "AsyncOpenAI", lambda **kwargs: fake_client)
    provider = ProviderOpenAITTSAPI(
        {
            "id": "openai_tts",
            "type": "openai_tts_api",
            "model": "gpt-4o-mini-tts",
            "api_key": "test-key",
            "openai-tts-voice": "alloy",
        },
        {},
    )
    provider.client = fake_client
    return provider


def test_get_audio_preserves_real_audio_extension(monkeypatch, tmp_path: Path):
    response = FakeStreamingResponse(
        chunks=[b"ID3", b"fake-mp3-audio"],
        headers={"content-type": "audio/mpeg"},
    )
    provider = make_provider(monkeypatch, response)
    monkeypatch.setattr(openai_tts_api_source, "get_astrbot_temp_path", lambda: str(tmp_path))

    path = asyncio.run(provider.get_audio("hello"))

    assert path.endswith(".mp3")
    assert Path(path).read_bytes() == b"ID3fake-mp3-audio"
    assert provider.client.audio.speech.with_streaming_response.calls[0]["response_format"] == "wav"


def test_get_audio_raises_clear_error_for_non_audio_payload(monkeypatch, tmp_path: Path):
    response = FakeStreamingResponse(
        chunks=[b'{"error":"unsupported response_format"}'],
        headers={"content-type": "application/json"},
    )
    provider = make_provider(monkeypatch, response)
    monkeypatch.setattr(openai_tts_api_source, "get_astrbot_temp_path", lambda: str(tmp_path))

    with pytest.raises(RuntimeError, match="unexpected content-type"):
        asyncio.run(provider.get_audio("hello"))
