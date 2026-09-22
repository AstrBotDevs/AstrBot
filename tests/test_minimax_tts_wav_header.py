import struct

import pytest

from astrbot.core.provider.sources.minimax_tts_api_source import (
    ProviderMiniMaxTTSAPI,
    _repair_wav_header,
)

FMT = struct.pack("<HHIIHH", 1, 1, 32000, 32000 * 2, 2, 16)
PAYLOAD = b"\x01\x02" * 1024


def _build_wav(riff_size: int, data_size: int) -> bytes:
    """Build a WAV file whose RIFF/data lengths are caller-chosen."""
    return b"".join(
        (
            b"RIFF",
            struct.pack("<I", riff_size),
            b"WAVE",
            b"fmt ",
            struct.pack("<I", len(FMT)),
            FMT,
            b"data",
            struct.pack("<I", data_size),
            PAYLOAD,
        )
    )


def test_placeholder_streamed_header_is_repaired():
    """MiniMax streams 0xFFFFFFFF length placeholders; rebuild them from the file."""
    streamed = _build_wav(0xFFFFFFFF, 0xFFFFFFFF)

    repaired = _repair_wav_header(streamed)

    assert struct.unpack_from("<I", repaired, 4)[0] == len(repaired) - 8
    data_size = struct.unpack_from("<I", repaired, repaired.index(b"data") + 4)[0]
    assert data_size == len(PAYLOAD)
    assert repaired[repaired.index(b"data") + 8 :] == PAYLOAD
    assert repaired[repaired.index(b"fmt ") + 8 :][: len(FMT)] == FMT


def test_consistent_header_is_left_untouched():
    consistent = _build_wav(
        4 + (8 + len(FMT)) + (8 + len(PAYLOAD)),
        len(PAYLOAD),
    )

    assert _repair_wav_header(consistent) == consistent


def test_non_wav_bytes_pass_through():
    for blob in (b"", b"ID3(mp3 bytes)", b"RIFF", b"RIFF\xff\xff\xff\xff"):
        assert _repair_wav_header(blob) == blob


@pytest.mark.asyncio
async def test_audio_play_repairs_streamed_wav():
    """_audio_play reassembles the hex SSE stream into a valid WAV file."""
    provider = ProviderMiniMaxTTSAPI(
        {"api_key": "k", "minimax-group-id": "g"},
        {},
    )
    streamed = _build_wav(0xFFFFFFFF, 0xFFFFFFFF)
    hex_chunks = [streamed[i : i + 2048].hex() for i in range(0, len(streamed), 2048)]

    async def audio_stream():
        for chunk in hex_chunks:
            yield chunk

    audio = await provider._audio_play(audio_stream())

    assert struct.unpack_from("<I", audio, 4)[0] == len(audio) - 8
    data_size = struct.unpack_from("<I", audio, audio.index(b"data") + 4)[0]
    assert data_size == len(PAYLOAD)
