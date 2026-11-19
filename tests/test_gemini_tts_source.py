import io
import wave
from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources import gemini_tts_source
from astrbot.core.provider.sources.gemini_tts_source import ProviderGeminiTTSAPI

PCM = b"\x01\x00\xff\xff" * 240


def _make_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)
    return buf.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [PCM, _make_wav(PCM)], ids=["pcm", "wav"])
async def test_get_audio_writes_playable_wav(payload, tmp_path, monkeypatch):
    monkeypatch.setattr(gemini_tts_source, "get_astrbot_temp_path", lambda: tmp_path)
    provider = ProviderGeminiTTSAPI({"gemini_tts_api_key": "test-key"}, {})

    async def fake_generate_content(**kwargs):
        part = SimpleNamespace(inline_data=SimpleNamespace(data=payload))
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))]
        )

    await provider.client.aclose()
    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content=fake_generate_content)
    )

    path = await provider.get_audio("hello")

    with wave.open(path, "rb") as wf:
        assert wf.getframerate() == 24000
        assert wf.readframes(wf.getnframes()) == PCM
