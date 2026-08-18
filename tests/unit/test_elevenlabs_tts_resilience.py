"""Offline resilience contracts for the ElevenLabs TTS adapter."""

import asyncio
import logging
from pathlib import Path

import pytest

from astrbot.core.provider.sources import elevenlabs_tts_source
from astrbot.core.provider.sources.elevenlabs_tts_source import (
    ProviderElevenLabsTTSAPI,
)

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=elevenlabs-api-key "
    "Bearer elevenlabs-bearer-token "
    "password=elevenlabs-password "
    "https://internal.example/private/tts "
    "C:\\private\\elevenlabs\\secret.wav "
    "/srv/astrbot/private/elevenlabs.wav"
)
_SENSITIVE_VALUES = (
    "elevenlabs-api-key",
    "elevenlabs-bearer-token",
    "elevenlabs-password",
    "internal.example",
    "C:\\private\\elevenlabs\\secret.wav",
    "/srv/astrbot/private/elevenlabs.wav",
)
_AUDIO_ERROR = "ElevenLabs TTS audio generation failed."


class _Response:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content: object = b"audio",
        content_type: str = "audio/mpeg",
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}
        self.text = text


class _Client:
    def __init__(self, result: _Response | BaseException) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.closed = False
        self.close_error: BaseException | None = None

    async def post(self, url: str, **kwargs: object) -> _Response:
        self.calls.append((url, kwargs))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    async def aclose(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def _provider(client: _Client) -> ProviderElevenLabsTTSAPI:
    provider = ProviderElevenLabsTTSAPI.__new__(ProviderElevenLabsTTSAPI)
    provider.api_key = "test-api-key"
    provider.api_base = "https://elevenlabs.example.test/v1"
    provider.voice_id = "test-voice"
    provider.model_name = "eleven_multilingual_v2"
    provider.output_format = "mp3_44100_128"
    provider.voice_settings = {"stability": 0.5}
    provider.client = client
    return provider


def _assert_redacted(*values: object) -> None:
    for value in values:
        rendered = str(value)
        for sensitive_value in _SENSITIVE_VALUES:
            assert sensitive_value not in rendered


def test_elevenlabs_constructor_does_not_log_proxy_contents(
    monkeypatch, caplog
) -> None:
    client = _Client(_Response())
    captured: dict[str, object] = {}

    def _new_client(**kwargs: object) -> _Client:
        captured.update(kwargs)
        return client

    monkeypatch.setattr(elevenlabs_tts_source.httpx, "AsyncClient", _new_client)

    with caplog.at_level(logging.INFO, logger="astrbot"):
        provider = ProviderElevenLabsTTSAPI(
            {
                "type": "elevenlabs_tts_api",
                "api_base": "https://internal.example/private/tts",
                "proxy_mode": "custom",
                "proxy_url": _SENSITIVE_ERROR,
            },
            {},
        )

    assert provider.client is client
    assert captured["proxy"] == _SENSITIVE_ERROR
    _assert_redacted(caplog.text)


def test_elevenlabs_hides_client_initialization_error(monkeypatch, caplog) -> None:
    def _raise_client_error(**_kwargs: object) -> None:
        raise RuntimeError(_SENSITIVE_ERROR)

    monkeypatch.setattr(
        elevenlabs_tts_source.httpx,
        "AsyncClient",
        _raise_client_error,
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError) as caught:
            ProviderElevenLabsTTSAPI(
                {"type": "elevenlabs_tts_api", "proxy": _SENSITIVE_ERROR},
                {},
            )

    assert str(caught.value) == "ElevenLabs TTS client initialization failed."
    assert caught.value.__cause__ is None
    _assert_redacted(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_elevenlabs_returns_nonempty_audio_and_correct_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    client = _Client(_Response(content=b"audio-data"))
    provider = _provider(client)
    monkeypatch.setattr(
        elevenlabs_tts_source,
        "get_astrbot_temp_path",
        lambda: tmp_path,
    )

    output_path = Path(await provider.get_audio("hello"))

    try:
        assert output_path.read_bytes() == b"audio-data"
        assert client.calls == [
            (
                "https://elevenlabs.example.test/v1/text-to-speech/test-voice",
                {
                    "headers": {
                        "xi-api-key": "test-api-key",
                        "Content-Type": "application/json",
                    },
                    "params": {"output_format": "mp3_44100_128"},
                    "json": {
                        "text": "hello",
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {"stability": 0.5},
                    },
                },
            )
        ]
    finally:
        output_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_elevenlabs_hides_transport_exception_and_private_url(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    provider = _provider(_Client(RuntimeError(_SENSITIVE_ERROR)))
    provider.api_base = "https://internal.example/private/tts"
    monkeypatch.setattr(
        elevenlabs_tts_source,
        "get_astrbot_temp_path",
        lambda: tmp_path,
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError) as caught:
            await provider.get_audio("hello")

    assert str(caught.value) == _AUDIO_ERROR
    assert caught.value.__cause__ is None
    assert not list(tmp_path.glob("elevenlabs_tts_api_*"))
    _assert_redacted(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_elevenlabs_hides_http_error_body(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    provider = _provider(_Client(_Response(status_code=502, text=_SENSITIVE_ERROR)))
    monkeypatch.setattr(
        elevenlabs_tts_source,
        "get_astrbot_temp_path",
        lambda: tmp_path,
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError) as caught:
            await provider.get_audio("hello")

    assert str(caught.value) == _AUDIO_ERROR
    assert caught.value.__cause__ is None
    assert not list(tmp_path.glob("elevenlabs_tts_api_*"))
    _assert_redacted(caught.value, caplog.text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"", "audio/mpeg"),
        (_SENSITIVE_ERROR.encode(), "application/json"),
        (_SENSITIVE_ERROR, "audio/mpeg"),
    ],
)
async def test_elevenlabs_rejects_empty_or_malformed_audio(
    monkeypatch,
    tmp_path: Path,
    caplog,
    content: object,
    content_type: str,
) -> None:
    provider = _provider(_Client(_Response(content=content, content_type=content_type)))
    monkeypatch.setattr(
        elevenlabs_tts_source,
        "get_astrbot_temp_path",
        lambda: tmp_path,
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError) as caught:
            await provider.get_audio("hello")

    assert str(caught.value) == _AUDIO_ERROR
    assert caught.value.__cause__ is None
    assert not list(tmp_path.glob("elevenlabs_tts_api_*"))
    _assert_redacted(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_elevenlabs_cancellation_removes_partially_written_audio(
    monkeypatch,
    tmp_path: Path,
) -> None:
    provider = _provider(_Client(_Response(content=b"audio-data")))
    original_write_bytes = Path.write_bytes

    def _write_partial_then_cancel(path: Path, data: bytes) -> int:
        original_write_bytes(path, data[:1])
        raise asyncio.CancelledError

    monkeypatch.setattr(
        elevenlabs_tts_source,
        "get_astrbot_temp_path",
        lambda: tmp_path,
    )
    monkeypatch.setattr(Path, "write_bytes", _write_partial_then_cancel)

    with pytest.raises(asyncio.CancelledError):
        await provider.get_audio("hello")

    assert not list(tmp_path.glob("elevenlabs_tts_api_*"))


@pytest.mark.asyncio
async def test_elevenlabs_terminate_closes_and_drops_client() -> None:
    client = _Client(_Response())
    provider = _provider(client)

    await provider.terminate()

    assert client.closed
    assert provider.client is None


@pytest.mark.asyncio
async def test_elevenlabs_terminate_redacts_close_error_and_drops_client(
    caplog,
) -> None:
    client = _Client(_Response())
    client.close_error = RuntimeError(_SENSITIVE_ERROR)
    provider = _provider(client)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        await provider.terminate()

    assert client.closed
    assert provider.client is None
    _assert_redacted(caplog.text)


@pytest.mark.asyncio
async def test_elevenlabs_terminate_propagates_cancellation_after_dropping_client() -> (
    None
):
    client = _Client(_Response())
    client.close_error = asyncio.CancelledError()
    provider = _provider(client)

    with pytest.raises(asyncio.CancelledError):
        await provider.terminate()

    assert client.closed
    assert provider.client is None


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (
            {"elevenlabs-tts-output-format": "pcm_16000"},
            "ElevenLabs raw audio output formats are not supported by this provider. "
            "Use an mp3, wav, or opus output format instead.",
        ),
        (
            {"elevenlabs-tts-stability": "1.1"},
            "elevenlabs-tts-stability must be between 0 and 1.",
        ),
        (
            {"elevenlabs-tts-use-speaker-boost": "not-a-boolean"},
            "elevenlabs-tts-use-speaker-boost must be a boolean value.",
        ),
    ],
)
def test_elevenlabs_keeps_configuration_errors_specific(
    monkeypatch,
    config: dict[str, object],
    message: str,
) -> None:
    monkeypatch.setattr(
        elevenlabs_tts_source.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(_Response()),
    )

    with pytest.raises(ValueError) as caught:
        ProviderElevenLabsTTSAPI({"type": "elevenlabs_tts_api", **config}, {})

    assert str(caught.value) == message
