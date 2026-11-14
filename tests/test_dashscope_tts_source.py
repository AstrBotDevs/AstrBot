"""Tests for the DashScope TTS audio download path (#10627).

Qwen TTS returns an audio URL that the provider downloads with aiohttp. When
that URL answers with an HTTP error, the error body is still a valid byte
sequence, so without an explicit status check the provider treats it as
synthesized audio and writes it to disk as a ``.wav`` file. ``get_audio``
therefore has to see a download failure and raise instead of emitting garbage.
"""

from unittest.mock import Mock

import aiohttp
import pytest

from astrbot.core.provider.sources.dashscope_tts import ProviderDashscopeTTSAPI

AUDIO_URL = "https://example.invalid/qwen-tts/audio.wav"


class _FakeResponse:
    """Minimal stand-in for the aiohttp response used as an async context."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=Mock(real_url=AUDIO_URL),
                history=(),
                status=self.status,
                message="upstream error",
            )

    async def read(self) -> bytes:
        return self._body


class _FakeSession:
    """Minimal stand-in for ``aiohttp.ClientSession``."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def get(self, url, **kwargs):
        return self._response


@pytest.fixture
def provider() -> ProviderDashscopeTTSAPI:
    return ProviderDashscopeTTSAPI(
        {"model": "qwen-tts", "api_key": "sk-test", "dashscope_tts_voice": "Cherry"},
        {},
    )


@pytest.mark.asyncio
async def test_http_error_body_is_not_returned_as_audio(provider, monkeypatch):
    error_body = b'{"code":"InternalError","message":"upstream failure"}'
    response = _FakeResponse(status=500, body=error_body)
    monkeypatch.setattr(
        aiohttp, "ClientSession", lambda **kwargs: _FakeSession(response)
    )

    assert await provider._download_audio_from_url(AUDIO_URL) is None


@pytest.mark.asyncio
async def test_successful_download_returns_audio_bytes(provider, monkeypatch):
    audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt "
    response = _FakeResponse(status=200, body=audio_bytes)
    monkeypatch.setattr(
        aiohttp, "ClientSession", lambda **kwargs: _FakeSession(response)
    )

    assert await provider._download_audio_from_url(AUDIO_URL) == audio_bytes
