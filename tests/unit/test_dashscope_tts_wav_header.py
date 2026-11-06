import io
import struct
import wave

import pytest

from astrbot.core.provider.sources import dashscope_tts
from astrbot.core.provider.sources.dashscope_tts import ProviderDashscopeTTSAPI


def _streamed_wav(frames: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(frames)
    data = bytearray(buffer.getvalue())
    # Mimic the "unknown length" placeholders written by streamed synthesis.
    struct.pack_into("<I", data, 4, 0x7FFFFFFF - 1)
    struct.pack_into("<I", data, 40, 0x7FFFFFFF - 0x24)
    return bytes(data)


@pytest.mark.asyncio
async def test_get_audio_rewrites_placeholder_wav_sizes(tmp_path, monkeypatch):
    frames = b"\x01\x00" * 2400
    monkeypatch.setattr(dashscope_tts, "get_astrbot_temp_path", lambda: str(tmp_path))
    provider = ProviderDashscopeTTSAPI(
        {"id": "tts", "type": "dashscope_tts", "model": "cosyvoice-v3-flash"}, {}
    )

    async def fake_cosyvoice(model, text):
        return _streamed_wav(frames), ".wav"

    monkeypatch.setattr(provider, "_synthesize_with_cosyvoice", fake_cosyvoice)

    path = await provider.get_audio("hello")

    with open(path, "rb") as f:
        data = f.read()
    assert struct.unpack_from("<I", data, 4)[0] == len(data) - 8
    assert struct.unpack_from("<I", data, 40)[0] == len(frames)
    with wave.open(path, "rb") as wav:
        assert wav.readframes(wav.getnframes()) == frames
