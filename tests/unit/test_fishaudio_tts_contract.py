"""Offline error, cancellation, and file-cleanup contracts for FishAudio TTS."""

import asyncio
import logging
from pathlib import Path

import pytest

from astrbot.core.provider.sources import fishaudio_tts_api_source
from astrbot.core.provider.sources.fishaudio_tts_api_source import (
    ProviderFishAudioTTSAPI,
)

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=fishaudio-api-key "
    "Bearer fishaudio-bearer "
    "password=fishaudio-password "
    "https://internal.example/fishaudio "
    "C:\\private\\fishaudio.txt "
    "/srv/astrbot/fishaudio.json"
)
_SENSITIVE_VALUES = (
    "fishaudio-api-key",
    "fishaudio-bearer",
    "fishaudio-password",
    "https://internal.example/fishaudio",
    "C:\\private\\fishaudio.txt",
    "/srv/astrbot/fishaudio.json",
)


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        for value in _SENSITIVE_VALUES:
            assert value not in str(text)


class _Response:
    def __init__(
        self,
        *,
        status_code: int,
        content_type: str = "application/json",
        chunks: tuple[bytes | BaseException, ...] = (),
    ) -> None:
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.chunks = chunks

    async def aiter_bytes(self):
        for chunk in self.chunks:
            if isinstance(chunk, BaseException):
                raise chunk
            yield chunk

    async def aread(self) -> bytes:
        return _SENSITIVE_ERROR.encode()


class _Stream:
    def __init__(self, response: _Response | BaseException) -> None:
        self.response = response

    async def __aenter__(self) -> _Response:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Client:
    def __init__(self, response: _Response | BaseException) -> None:
        self.response = response

    def stream(self, *_args: object, **_kwargs: object) -> _Stream:
        return _Stream(self.response)


def _provider() -> ProviderFishAudioTTSAPI:
    provider = ProviderFishAudioTTSAPI.__new__(ProviderFishAudioTTSAPI)
    provider.reference_id = "a" * 32
    provider.character = "test"
    provider.api_base = "https://fishaudio.example.test/v1"
    provider.timeout = 1
    provider.proxy = ""
    provider.headers = {"Authorization": "Bearer test-key"}
    return provider


def _patch_client(
    monkeypatch: pytest.MonkeyPatch,
    response: _Response | BaseException,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        fishaudio_tts_api_source, "AsyncClient", lambda **_kwargs: _Client(response)
    )
    monkeypatch.setattr(
        fishaudio_tts_api_source, "get_astrbot_temp_path", lambda: str(tmp_path)
    )


@pytest.mark.parametrize(
    ("configured_model", "expected_model"),
    [(None, "s2-pro"), ("", "s2-pro"), ("custom-model", "custom-model")],
)
def test_fishaudio_tts_sets_a_model_header(
    configured_model: str | None,
    expected_model: str,
) -> None:
    provider_config = {"type": "fishaudio_tts_api"}
    if configured_model is not None:
        provider_config["model"] = configured_model

    provider = ProviderFishAudioTTSAPI(provider_config, {})

    assert provider.get_model() == expected_model
    assert provider.headers["model"] == expected_model


def test_fishaudio_tts_does_not_log_proxy_credentials(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="astrbot"):
        ProviderFishAudioTTSAPI(
            {
                "type": "fishaudio_tts_api",
                "proxy": _SENSITIVE_ERROR,
            },
            {},
        )

    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_fishaudio_tts_hides_http_error_from_logs_and_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog
) -> None:
    _patch_client(monkeypatch, _Response(status_code=500), tmp_path)

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(
            RuntimeError, match="FishAudio TTS audio generation failed"
        ) as caught:
            await _provider().get_audio("text")

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)
    assert list(tmp_path.glob("*.wav")) == []


@pytest.mark.asyncio
async def test_fishaudio_tts_rejects_empty_audio_and_cleans_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_client(
        monkeypatch,
        _Response(status_code=200, content_type="audio/wav"),
        tmp_path,
    )

    with pytest.raises(RuntimeError, match="FishAudio TTS audio generation failed"):
        await _provider().get_audio("text")

    assert list(tmp_path.glob("*.wav")) == []


@pytest.mark.asyncio
async def test_fishaudio_tts_cancellation_cleans_partial_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_client(
        monkeypatch,
        _Response(
            status_code=200,
            content_type="audio/wav",
            chunks=(b"partial", asyncio.CancelledError()),
        ),
        tmp_path,
    )

    with pytest.raises(asyncio.CancelledError):
        await _provider().get_audio("text")

    assert list(tmp_path.glob("*.wav")) == []


@pytest.mark.asyncio
async def test_fishaudio_tts_hides_transport_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog
) -> None:
    _patch_client(monkeypatch, RuntimeError(_SENSITIVE_ERROR), tmp_path)

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(
            RuntimeError, match="FishAudio TTS audio generation failed"
        ) as caught:
            await _provider().get_audio("text")

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)
