import struct

import pytest

from astrbot.core.provider.sources.minimax_tts_api_source import (
    WAV_SIZE_PLACEHOLDER,
    ProviderMiniMaxTTSAPI,
    _patch_streamed_wav_header,
)

FMT_CHUNK_SIZE = 24  # 8-byte chunk header + 16-byte PCM fmt body


def _make_wav(
    payload: bytes = b"\x00\x01",
    riff_size: int = WAV_SIZE_PLACEHOLDER,
    data_size: int = WAV_SIZE_PLACEHOLDER,
    extra_chunks: bytes = b"",
) -> bytes:
    """Build a minimal PCM WAV file, optionally with placeholder sizes."""
    fmt = struct.pack("<HHIIHH", 1, 1, 32000, 64000, 2, 16)
    chunks = (
        b"WAVE"
        + extra_chunks
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"data"
        + struct.pack("<I", data_size)
        + payload
    )
    return b"RIFF" + struct.pack("<I", riff_size) + chunks


def _data_size_offset(extra_chunks_len: int) -> int:
    # RIFF(4) + size(4) + WAVE(4) + extra chunks + fmt chunk + data id(4)
    return 12 + extra_chunks_len + FMT_CHUNK_SIZE + 4


class TestPatchStreamedWavHeader:
    def test_placeholder_sizes_repaired(self):
        payload = b"\x00\x01" * 1000
        fixed = _patch_streamed_wav_header(_make_wav(payload=payload))

        off = _data_size_offset(0)
        assert int.from_bytes(fixed[4:8], "little") == len(fixed) - 8
        assert int.from_bytes(fixed[off : off + 4], "little") == len(payload)
        assert fixed != _make_wav(payload=payload)

    def test_valid_wav_unchanged(self):
        payload = b"\x00\x01" * 1000
        wav = _make_wav(
            payload=payload,
            riff_size=44 + len(payload) - 8,
            data_size=len(payload),
        )
        assert _patch_streamed_wav_header(wav) == wav

    def test_non_wav_input_unchanged(self):
        for blob in (
            b"",
            b"\x00" * 64,
            b"RIFF\x00\x00\x00\x00",
            b"RIFF\x00\x00\x00\x00WAVE",
            b"NOTWAV" + b"\x00" * 32,
        ):
            assert _patch_streamed_wav_header(blob) == blob

    def test_riff_placeholder_with_valid_data_size_patched(self):
        # Mixed placeholder state: data size is already real but the RIFF
        # size is still the placeholder -- only RIFF gets rewritten.
        payload = b"\x00\x01" * 1000
        fixed = _patch_streamed_wav_header(
            _make_wav(
                payload=payload, riff_size=WAV_SIZE_PLACEHOLDER, data_size=len(payload)
            )
        )

        off = _data_size_offset(0)
        assert int.from_bytes(fixed[4:8], "little") == len(fixed) - 8
        assert int.from_bytes(fixed[off : off + 4], "little") == len(payload)

    def test_extra_chunks_before_data_still_patched(self):
        payload = b"\x00\x01" * 100
        info = b"INFOabcd"  # even length: no pad byte
        list_chunk = b"LIST" + struct.pack("<I", len(info)) + info
        fixed = _patch_streamed_wav_header(
            _make_wav(payload=payload, extra_chunks=list_chunk)
        )

        off = _data_size_offset(len(list_chunk))
        assert int.from_bytes(fixed[4:8], "little") == len(fixed) - 8
        assert int.from_bytes(fixed[off : off + 4], "little") == len(payload)

    def test_placeholder_size_before_data_left_untouched(self):
        # An un-walkable chunk before ``data`` must not be guessed around.
        junk = b"junk" + struct.pack("<I", WAV_SIZE_PLACEHOLDER) + b"abcd"
        wav = _make_wav(payload=b"xy", extra_chunks=junk)
        assert _patch_streamed_wav_header(wav) == wav

    def test_truncation_cases(self):
        # Truncated before the data chunk header: nothing to patch.
        wav = _make_wav(payload=b"abc")[:30]
        assert _patch_streamed_wav_header(wav) == wav
        # Truncated inside the data payload: the placeholder is still
        # replaced with whatever data actually arrived.
        wav = _make_wav(payload=b"abcdefgh")[:50]
        fixed = _patch_streamed_wav_header(wav)
        assert int.from_bytes(fixed[40:44], "little") == 6


def _hex_stream(data: bytes, chunk_size: int = 7):
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size].hex()


class TestGetAudioEndToEnd:
    @pytest.mark.asyncio
    async def test_get_audio_writes_valid_wav(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "astrbot.core.provider.sources.minimax_tts_api_source.get_astrbot_temp_path",
            lambda: str(tmp_path),
        )
        provider = ProviderMiniMaxTTSAPI(
            {"api_key": "test-key", "model": "speech-01"},
            {},
        )
        wav = _make_wav(payload=b"\x00\x01" * 1000)

        async def fake_stream(_text):
            for chunk in _hex_stream(wav):
                yield chunk

        provider._call_tts_stream = fake_stream

        path = await provider.get_audio("你好")

        with open(path, "rb") as f:
            data = f.read()
        assert int.from_bytes(data[4:8], "little") == len(data) - 8
        assert int.from_bytes(data[40:44], "little") == 2000
