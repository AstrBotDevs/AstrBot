from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from astrbot.core.provider.sources.whisper_api_source import ProviderOpenAIWhisperAPI


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


def test_init_passes_the_provider_proxy_to_the_http_client():
    proxy = "http://127.0.0.1:7890"
    http_client = MagicMock()

    with (
        patch(
            "astrbot.core.provider.sources.whisper_api_source.create_proxy_client",
            return_value=http_client,
        ) as create_proxy_client,
        patch(
            "astrbot.core.provider.sources.whisper_api_source.AsyncOpenAI"
        ) as async_openai,
    ):
        ProviderOpenAIWhisperAPI(
            provider_config={
                "id": "test-whisper-api",
                "type": "openai_whisper_api",
                "model": "whisper-1",
                "api_key": "test-key",
                "proxy": proxy,
            },
            provider_settings={},
        )

    create_proxy_client.assert_called_once_with(
        "OpenAI Whisper", proxy, httpx_module=ANY
    )
    assert async_openai.call_args.kwargs["http_client"] is http_client


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
        if output_path is None:
            output_path = str(tmp_path / "converted.wav")
        conversions.append((audio_path, output_path))
        Path(output_path).write_bytes(b"fake wav data")
        return output_path

    monkeypatch.setattr(
        "astrbot.core.utils.media_utils.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.media_utils.convert_audio_to_wav",
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
