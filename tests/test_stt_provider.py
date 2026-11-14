"""Regression tests for the STT health check contract (#10628).

``STTProvider.test()`` backs the provider health check. It used to accept
whatever ``get_text`` returned, so a provider that swallowed an upstream
failure and returned ``""`` was reported as healthy. The health check now
rejects an empty transcription.
"""

import pytest

from astrbot.core.provider.provider import STTProvider


class _StubSTTProvider(STTProvider):
    def __init__(self, transcription: str) -> None:
        super().__init__({}, {})
        self.transcription = transcription
        self.transcribed_audio: str | None = None

    async def get_text(self, audio_url: str) -> str:
        self.transcribed_audio = audio_url
        return self.transcription


@pytest.mark.asyncio
@pytest.mark.parametrize("transcription", ["", " \n\t "])
async def test_health_check_rejects_empty_transcription(transcription: str) -> None:
    provider = _StubSTTProvider(transcription)

    with pytest.raises(RuntimeError, match="empty transcription"):
        await provider.test()


@pytest.mark.asyncio
async def test_health_check_passes_for_non_empty_transcription() -> None:
    provider = _StubSTTProvider("hello world")

    await provider.test()

    assert provider.transcribed_audio is not None
    assert provider.transcribed_audio.replace("\\", "/").endswith(
        "samples/stt_health_check.wav"
    )
