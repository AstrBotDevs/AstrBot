from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import astrbot.core.provider.sources.whisper_api_source as whisper_api_source
from astrbot.core.provider.sources.whisper_api_source import ProviderOpenAIWhisperAPI


class _FakeAsyncOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.close = AsyncMock()


def _make_provider() -> ProviderOpenAIWhisperAPI:
    provider = ProviderOpenAIWhisperAPI(
        provider_config={
            "id": "test-whisper-api",
            "type": "openai_whisper_api",
            "model": "whisper-1",
            "api_key": "test-key",
        },
        provider_settings={},
    )
    provider.client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(
                create=AsyncMock(return_value=SimpleNamespace(text="transcribed text"))
            )
        ),
        close=AsyncMock(),
    )
    return provider


def test_provider_passes_configured_proxy_to_openai_http_client(monkeypatch):
    captured: dict[str, object] = {}
    fake_http_client = SimpleNamespace(aclose=AsyncMock())

    def fake_create_proxy_client(
        provider_label: str,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        verify=None,
        httpx_module=None,
    ):
        captured["provider_label"] = provider_label
        captured["proxy"] = proxy
        captured["headers"] = headers
        captured["httpx_module"] = httpx_module
        return fake_http_client

    monkeypatch.setattr(whisper_api_source, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(
        whisper_api_source,
        "create_proxy_client",
        fake_create_proxy_client,
    )

    provider = ProviderOpenAIWhisperAPI(
        provider_config={
            "id": "test-whisper-api",
            "type": "openai_whisper_api",
            "model": "whisper-1",
            "api_key": "test-key",
            "api_base": "https://api.example.com/v1",
            "proxy": "http://127.0.0.1:7890",
            "timeout": 30,
        },
        provider_settings={},
    )

    assert provider.client.kwargs["api_key"] == "test-key"
    assert provider.client.kwargs["base_url"] == "https://api.example.com/v1"
    assert provider.client.kwargs["timeout"] == 30
    assert provider.client.kwargs["http_client"] is fake_http_client
    assert set(provider.client.kwargs) == {
        "api_key",
        "base_url",
        "timeout",
        "http_client",
    }
    assert provider.http_client is fake_http_client
    assert captured["provider_label"] == "OpenAI Whisper"
    assert captured["proxy"] == "http://127.0.0.1:7890"
    assert captured["headers"] is None
    assert captured["httpx_module"] is not None


def test_provider_uses_default_http_client_when_proxy_missing(monkeypatch):
    captured: dict[str, object] = {}
    fake_http_client = SimpleNamespace(aclose=AsyncMock())

    def fake_create_proxy_client(
        provider_label: str,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        verify=None,
        httpx_module=None,
    ):
        captured["provider_label"] = provider_label
        captured["proxy"] = proxy
        captured["headers"] = headers
        captured["httpx_module"] = httpx_module
        return fake_http_client

    monkeypatch.setattr(whisper_api_source, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(
        whisper_api_source,
        "create_proxy_client",
        fake_create_proxy_client,
    )

    provider = ProviderOpenAIWhisperAPI(
        provider_config={
            "id": "test-whisper-api",
            "type": "openai_whisper_api",
            "model": "whisper-1",
            "api_key": "test-key",
        },
        provider_settings={},
    )

    assert provider.client.kwargs["http_client"] is fake_http_client
    assert set(provider.client.kwargs) == {
        "api_key",
        "base_url",
        "timeout",
        "http_client",
    }
    assert provider.http_client is fake_http_client
    assert captured["provider_label"] == "OpenAI Whisper"
    assert captured["proxy"] is None
    assert captured["headers"] is None


@pytest.mark.asyncio
async def test_terminate_closes_openai_client_and_custom_http_client(monkeypatch):
    fake_http_client = SimpleNamespace(aclose=AsyncMock())

    monkeypatch.setattr(whisper_api_source, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(
        whisper_api_source,
        "create_proxy_client",
        lambda *args, **kwargs: fake_http_client,
    )

    provider = ProviderOpenAIWhisperAPI(
        provider_config={
            "id": "test-whisper-api",
            "type": "openai_whisper_api",
            "model": "whisper-1",
            "api_key": "test-key",
        },
        provider_settings={},
    )

    await provider.terminate()

    provider.client.close.assert_awaited_once()
    fake_http_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_text_converts_opus_files_to_wav_before_transcription(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    provider = _make_provider()
    opus_path = tmp_path / "voice.opus"
    opus_path.write_bytes(b"fake opus data")

    conversions: list[tuple[str, str]] = []

    async def fake_convert_audio_to_wav(
        audio_path: str, output_path: str | None = None
    ):
        assert output_path is not None
        conversions.append((audio_path, output_path))
        Path(output_path).write_bytes(b"fake wav data")
        return output_path

    monkeypatch.setattr(
        "astrbot.core.provider.sources.whisper_api_source.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.whisper_api_source.convert_audio_to_wav",
        fake_convert_audio_to_wav,
    )

    try:
        result = await provider.get_text(str(opus_path))

        assert result == "transcribed text"
        assert conversions and conversions[0][0] == str(opus_path)
        converted_path = Path(conversions[0][1])
        assert converted_path.suffix == ".wav"
        assert not converted_path.exists()

        create_mock = provider.client.audio.transcriptions.create
        create_mock.assert_awaited_once()
        file_arg = create_mock.await_args.kwargs["file"]
        assert file_arg[0] == "audio.wav"
        assert file_arg[1].name.endswith(".wav")
        file_arg[1].close()
    finally:
        await provider.terminate()
