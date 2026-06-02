from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


@pytest.mark.asyncio
async def test_get_text_converts_opus_files_to_wav_before_transcription(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    provider = _make_provider()
    opus_path = tmp_path / "voice.opus"
    opus_path.write_bytes(b"fake opus data")

    conversions: list[tuple[str, str]] = []

    async def fake_convert_audio_to_wav(audio_path: str, output_path: str | None = None):
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
