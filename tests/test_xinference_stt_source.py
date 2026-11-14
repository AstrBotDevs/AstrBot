"""Regression tests for the Xinference STT failure contract (#10628).

The provider used to log upstream failures and return an empty string, which
made an uninitialized or broken provider indistinguishable from silence.
Failures now propagate to the caller.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.core.provider.sources.xinference_stt_provider import (
    ProviderXinferenceSTT,
)


def _make_provider() -> ProviderXinferenceSTT:
    """Build a provider without touching ``initialize()`` (no network access)."""
    return ProviderXinferenceSTT(
        provider_config={
            "api_base": "http://127.0.0.1:9997/",
            "model": "whisper-large-v3",
        },
        provider_settings={},
    )


class _StubResolver:
    """Stand-in for ``MediaResolver`` that skips decoding and returns ``payload``."""

    payload = b""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    @asynccontextmanager
    async def as_path(self, **_kwargs: object):
        yield SimpleNamespace(read_bytes=lambda: self.payload)


class _ErrorResponse:
    """Minimal aiohttp response for a failed transcription request."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def text(self) -> str:
        return self._body


@pytest.mark.asyncio
async def test_get_text_raises_when_provider_is_not_initialized() -> None:
    # A failed initialize() leaves model_uid/client at None.
    provider = _make_provider()

    with pytest.raises(RuntimeError, match="not initialized"):
        await provider.get_text("audio.wav")


@pytest.mark.asyncio
async def test_get_text_rejects_empty_audio(monkeypatch) -> None:
    provider = _make_provider()
    provider.model_uid = "whisper-large-v3-uid"
    provider.client = SimpleNamespace(session=Mock(), _headers={})
    monkeypatch.setattr(
        "astrbot.core.provider.sources.xinference_stt_provider.MediaResolver",
        _StubResolver,
    )

    with pytest.raises(ValueError, match="Audio bytes are empty"):
        await provider.get_text("audio.wav")


@pytest.mark.asyncio
async def test_get_text_raises_on_non_200_response(monkeypatch) -> None:
    provider = _make_provider()
    session = SimpleNamespace(post=Mock(return_value=_ErrorResponse(500, "boom")))
    provider.model_uid = "whisper-large-v3-uid"
    provider.client = SimpleNamespace(session=session, _headers={})
    monkeypatch.setattr(
        "astrbot.core.provider.sources.xinference_stt_provider.MediaResolver",
        _StubResolver,
    )
    monkeypatch.setattr(_StubResolver, "payload", b"RIFF" + b"\x00" * 32)

    with pytest.raises(RuntimeError, match="status 500"):
        await provider.get_text("audio.wav")
