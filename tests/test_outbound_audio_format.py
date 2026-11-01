"""Regression tests for outbound record audio payloads.

Before v4.26.0 every outbound record was transcoded to WAV before being base64
encoded. For a long MP3 that inflates the payload by roughly 4.4x, which can
exceed platform frame limits (OneBot WebSocket frames, for example, top out at
100 MiB) and drops the connection. MP3 payloads therefore keep their original
bytes, other containers still resolve to WAV, and the platform adapters derive
the MIME type / file extension from the bytes they actually send.
"""

import base64
import functools
import http.server
import io
import shutil
import threading
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Record
from astrbot.core.platform.sources.satori.satori_event import SatoriPlatformEvent
from astrbot.core.platform.sources.webchat import webchat_event as webchat_event_module
from astrbot.core.utils import media_utils
from astrbot.dashboard.services.chat_service import ChatService

# 0.12 s, 440 Hz mono 24 kbps MP3, embedded so the passthrough tests do not need
# ffmpeg to be installed.
MP3_SAMPLE_BASE64 = (
    "SUQzBAAAAAAAIlRTU0UAAAAOAAADTGF2ZjYzLjQuMTAwAAAAAAAAAAAAAAD/4zjAAAAAAAAAAAAA"
    "SW5mbwAAAA8AAAAEAAAEOABmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmaZmZmZmZmZmZmZmZmZmZmZ"
    "mZmZmZmZmZmZzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzP//////////////////////////////"
    "//8AAAAATGF2YzYzLjYuAAAAAAAAAAAAAAAAAvMAAAAAAAAABDirOssBAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/4zjEACqCIlABWhgBLllyy5ZcsuWgHQfT"
    "HWOoIkIgELkFyC8CDigixEx0JZbMsmAgZcdt7Kc4CCJGmVXnFsnp6n79n11nZhmpFqasnXgXcLwI"
    "qLEa5LM68NuW5b/xu3pzCAAAAJXABG7noAAYt/rhwMAAEREQIAAYG7u7hwMAAEREQIIAwN3d3cWA"
    "CEREREFu7u7u4gAAAAADw8PDwwAAAAADw8PDwwAAAAADw8PDwwAAAAQHh48CAABmAmBoYHIHRglg"
    "zGAwCDVs1q3//mCQCeYMwRZgVgz/4zjEITIbKkQZnqAARg7hJWpmrGf//MNMSQwXAsTZiK+Mj0aS"
    "AjAuAUNmkmow4ALPMBsFc1pFDzDHBBA230D+awPFrAx7ADZrgNe0MnNTFkqPgAFwMwXAyx0BIgDF"
    "igMWOCxEDBAVOvV/4GCChswNxA2sH6hcKFoIpINXBq7///GNEFRBUcoUELmIaLlHNJoc4i3//+3M"
    "SKk6ZF42WXWUk9v////VrUpJaJipIyRRMQa//10qAClu2wAH/////++4b7hvuGuV9XqetYjcpg9f"
    "DYzTqDB2HPz/4zjEIzVcbqB/2TAAP/KZfKKs/SY26mVivlYzywzm4m4m4qLpA+kLlOJuJsxIgekQ"
    "PSIHopmSmYiFmJED0iB6RA9EmYiTMRJmJED1kC1kC1EylEylEylkC1kC1kC1EylEylEylkC1kC1k"
    "C1EylEylEylkC1kC1kC1EykCZyBOkyBqZA1MhKBM5AnSB9JmSmZKZkoH0gfSB9JmSmZKZkoH0gfS"
    "B9JmSmZKZkoH0gfSB9JmSmZKZkoH0gfSB+pmSnVIAFqVg2vlPlPsskbCRpknWRFE4sJ+oiX/4zjE"
    "GCZxinmSM8xlI9iXi9DVDtLYfYUeNAQGGCi1ESlkSlkW04tRItRJ1SyyJSzW2nynynRNhZrLNhKr"
    "ROdR1goESCQILBg0LBQIECQILBg0aTRAjaKVjUpNFdtFKS1KTRXKopSWMpNFMVRSkkspNFMVRSkk"
    "spNFMVRSkkspNFMVRSkkspNFqlFKa3KTYUxBTUUzLjEwMSAoYmV0YSAzKVVVVVVVVVVVVVVVVVVV"
    "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVU="
)
MP3_SAMPLE = base64.b64decode(MP3_SAMPLE_BASE64)

# 0.1 s silent Ogg/Opus, embedded so the "only MP3 is preserved" tests can run
# without ffmpeg creating the fixture (converting it still needs ffmpeg).
OGG_SAMPLE_BASE64 = (
    "T2dnUwACAAAAAAAAAABCIpsIAAAAABbc754BE09wdXNIZWFkAQE4AUAfAAAAAABPZ2dTAAAAAAAA"
    "AAAAAEIimwgBAAAA3v4CSgE8T3B1c1RhZ3MMAAAATGF2ZjYzLjQuMTAwAQAAABwAAABlbmNvZGVy"
    "PUxhdmM2My42LjEwMCBsaWJvcHVzT2dnUwAE+BMAAAAAAABCIpsIAgAAAL4sQiMGAwMDAwMDmP/+"
    "mP/+mP/+mP/+mP/+mP/+"
)
OGG_SAMPLE = base64.b64decode(OGG_SAMPLE_BASE64)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG_AVAILABLE,
    reason="ffmpeg is required to create/convert the test fixtures",
)


def _wav_bytes(sample_rate: int = 8000, duration_seconds: float = 0.05) -> bytes:
    """Build a small silent WAV payload in memory."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * int(sample_rate * duration_seconds))
    return buffer.getvalue()


def _write_media(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass


@pytest.fixture
def media_server(tmp_path):
    """Serve ``tmp_path`` over loopback HTTP for suffix-less URL tests."""
    handler = functools.partial(_QuietHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_mp3_record_base64_keeps_original_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    source = _write_media(tmp_path, "sample.mp3", MP3_SAMPLE)

    payload = await Record(file=str(source)).convert_to_base64()

    assert isinstance(payload, str)
    assert base64.b64decode(payload) == MP3_SAMPLE
    # No WAV transcoding happened: the temp directory only holds the source.
    assert [path.name for path in tmp_path.iterdir()] == ["sample.mp3"]


@pytest.mark.asyncio
async def test_wav_record_base64_returns_wav_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    wav_bytes = _wav_bytes()
    source = _write_media(tmp_path, "sample.wav", wav_bytes)

    payload = await Record(file=str(source)).convert_to_base64()

    assert base64.b64decode(payload) == wav_bytes


@pytest.mark.asyncio
@requires_ffmpeg
async def test_non_mp3_record_base64_still_inflates_to_wav(tmp_path, monkeypatch):
    """Known limitation: only MP3 is preserved, everything else still becomes WAV.

    This is the v4.26.0 behavior, not a regression fix: FLAC/OGG/AMR payloads keep
    the ~4.4x inflation for now, which is tracked separately.
    """
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    mp3_source = _write_media(tmp_path, "sample.mp3", MP3_SAMPLE)
    flac_source = tmp_path / "sample.flac"
    await media_utils.convert_audio_format(
        str(mp3_source), output_format="flac", output_path=str(flac_source)
    )
    flac_bytes = flac_source.read_bytes()

    payload = await Record(file=str(flac_source)).convert_to_base64()
    decoded = base64.b64decode(payload)

    assert decoded != flac_bytes
    assert decoded[:4] == b"RIFF"
    assert decoded[8:12] == b"WAVE"


@pytest.mark.asyncio
@requires_ffmpeg
async def test_record_file_path_still_forces_wav(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    source = _write_media(tmp_path, "sample.mp3", MP3_SAMPLE)

    file_path = await Record(file=str(source)).convert_to_file_path()
    resolved = Path(file_path)

    try:
        assert resolved.suffix == ".wav"
        wav_bytes = resolved.read_bytes()
        assert wav_bytes[:4] == b"RIFF"
        assert wav_bytes[8:12] == b"WAVE"
    finally:
        resolved.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_satori_record_mime_type_follows_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    mp3_source = _write_media(tmp_path, "sample.mp3", MP3_SAMPLE)
    wav_source = _write_media(tmp_path, "sample.wav", _wav_bytes())

    # The record branch does not touch instance state, so a bare instance is
    # enough to exercise the real method body.
    event = SatoriPlatformEvent.__new__(SatoriPlatformEvent)
    mp3_element = await event._convert_component_to_satori(Record(file=str(mp3_source)))
    static_mp3_element = await SatoriPlatformEvent._convert_component_to_satori_static(
        Record(file=str(mp3_source))
    )
    static_wav_element = await SatoriPlatformEvent._convert_component_to_satori_static(
        Record(file=str(wav_source))
    )

    mp3_prefix = "data:audio/mpeg;base64,"
    assert mp3_element.startswith(f'<audio src="{mp3_prefix}')
    assert static_mp3_element.startswith(f'<audio src="{mp3_prefix}')
    assert base64.b64decode(mp3_element[len('<audio src="') + len(mp3_prefix) : -3]) == (
        MP3_SAMPLE
    )
    assert static_wav_element.startswith('<audio src="data:audio/wav;base64,')


@pytest.mark.asyncio
async def test_webchat_record_attachment_uses_payload_extension(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(webchat_event_module, "attachments_dir", str(tmp_path))
    source = _write_media(tmp_path, "sample.mp3", MP3_SAMPLE)

    captured: list[dict] = []

    async def fake_put_back_queue(_request_id, payload, *_args, **_kwargs):
        captured.append(payload)
        return True

    with patch.object(
        webchat_event_module.webchat_queue_mgr, "put_back_queue", fake_put_back_queue
    ):
        await webchat_event_module.WebChatMessageEvent._send(
            "test-request",
            MessageChain([Record(file=str(source))]),
            session_id="test-session",
        )

    record_payloads = [item for item in captured if item.get("type") == "record"]
    assert len(record_payloads) == 1
    data = record_payloads[0]["data"]
    assert data.startswith("[RECORD]")
    filename = data.removeprefix("[RECORD]")
    assert filename.endswith(".mp3")
    assert (tmp_path / filename).read_bytes() == MP3_SAMPLE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "expected_mime_type"),
    [
        ("voice.mp3", "audio/mpeg"),
        ("voice.wav", "audio/wav"),
        ("voice.flac", "audio/flac"),
        ("voice.ogg", "audio/ogg"),
        ("voice.amr", "audio/amr"),
        ("voice.silk", "audio/silk"),
    ],
)
async def test_webchat_audio_content_type_matches_extension(
    tmp_path, monkeypatch, filename, expected_mime_type
):
    monkeypatch.setattr(
        "astrbot.dashboard.services.chat_service.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    service = ChatService.__new__(ChatService)
    service.attachments_dir = str(tmp_path / "attachments")
    service.webchat_img_dir = str(tmp_path / "webchat_images")
    attachment = tmp_path / "attachments" / filename
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_bytes(b"audio-bytes")

    resolved_path, mime_type = await service.resolve_webchat_file(filename)

    assert resolved_path == str(attachment.resolve(strict=False))
    assert mime_type == expected_mime_type


@pytest.mark.asyncio
async def test_webchat_unknown_extension_has_no_mime_type(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "astrbot.dashboard.services.chat_service.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    service = ChatService.__new__(ChatService)
    service.attachments_dir = str(tmp_path / "attachments")
    service.webchat_img_dir = str(tmp_path / "webchat_images")
    attachment = tmp_path / "attachments" / "voice.bin"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_bytes(b"audio-bytes")

    _resolved_path, mime_type = await service.resolve_webchat_file("voice.bin")

    assert mime_type is None


@pytest.mark.parametrize(
    ("header", "expected_mime_type"),
    [
        (b"ID3\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00", "audio/mpeg"),
        (b"\xff\xfb\x90\x64" + b"\x00" * 12, "audio/mpeg"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 4, "audio/wav"),
        (b"fLaC\x00\x00\x00\x22" + b"\x00" * 6, "audio/flac"),
        (b"OggS\x00\x02\x00\x00" + b"\x00" * 12, "audio/ogg"),
        (
            b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00\x1fOpusHead",
            "audio/opus",
        ),
        (b"#!AMR\x0a" + b"\x00" * 8, "audio/amr"),
        (b"\x02#!SILK_V3" + b"\x00" * 6, "audio/silk"),
        (b"not-an-audio-header", "audio/mpeg"),
        (b"", "audio/mpeg"),
        (None, "audio/mpeg"),
    ],
)
def test_detect_audio_mime_type(header, expected_mime_type):
    assert media_utils.detect_audio_mime_type(header) == expected_mime_type


def test_detect_audio_mime_type_from_base64_matches_bytes():
    for payload in (MP3_SAMPLE, _wav_bytes(), b"unknown-payload"):
        expected = media_utils.detect_audio_mime_type(payload)
        actual = media_utils.detect_audio_mime_type_from_base64(
            base64.b64encode(payload).decode()
        )
        assert actual == expected


def test_detect_audio_mime_type_from_invalid_base64():
    assert (
        media_utils.detect_audio_mime_type_from_base64("!!!!not-base64!!!!")
        == "audio/mpeg"
    )
    assert media_utils.detect_audio_mime_type_from_base64("") == "audio/mpeg"


def test_get_audio_magic_type_still_reports_formats(tmp_path):
    mp3_path = _write_media(tmp_path, "sample.mp3", MP3_SAMPLE)
    wav_path = _write_media(tmp_path, "sample.wav", _wav_bytes())
    unknown_path = _write_media(tmp_path, "sample.bin", b"unknown-payload")

    assert media_utils._get_audio_magic_type(str(mp3_path)) == "mp3"
    assert media_utils._get_audio_magic_type(str(wav_path)) == "wav"
    assert media_utils._get_audio_magic_type(str(unknown_path)) == ""


@pytest.mark.asyncio
async def test_aiocqhttp_record_frame_keeps_mp3_payload(tmp_path, monkeypatch):
    pytest.importorskip("aiocqhttp")
    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
        AiocqhttpMessageEvent,
    )

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    source = _write_media(tmp_path, "sample.mp3", MP3_SAMPLE)

    segment = await AiocqhttpMessageEvent._from_segment_to_dict(
        Record(file=str(source))
    )

    assert segment["type"] == "record"
    assert segment["data"]["file"].startswith("base64://")
    payload = segment["data"]["file"].removeprefix("base64://")
    assert base64.b64decode(payload) == MP3_SAMPLE


@pytest.mark.asyncio
@requires_ffmpeg
async def test_base64_ogg_payload_is_converted_to_wav(tmp_path, monkeypatch):
    """A base64 payload has no suffix, so only the bytes may decide the format."""
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))

    payload = await Record.fromBase64(OGG_SAMPLE_BASE64).convert_to_base64()
    decoded = base64.b64decode(payload)

    assert decoded != OGG_SAMPLE
    assert decoded[:4] == b"RIFF"
    assert decoded[8:12] == b"WAVE"


@pytest.mark.asyncio
@requires_ffmpeg
async def test_suffixless_url_ogg_matches_suffixed_url(
    tmp_path, monkeypatch, media_server
):
    """A signed CDN URL without a suffix must behave like the ``.ogg`` one."""
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    _write_media(tmp_path, "voice", OGG_SAMPLE)
    _write_media(tmp_path, "voice.ogg", OGG_SAMPLE)

    without_suffix = base64.b64decode(
        await Record(file=f"{media_server}/voice").convert_to_base64()
    )
    with_suffix = base64.b64decode(
        await Record(file=f"{media_server}/voice.ogg").convert_to_base64()
    )

    assert without_suffix == with_suffix
    assert without_suffix[:4] == b"RIFF"
    assert without_suffix[8:12] == b"WAVE"


@pytest.mark.asyncio
async def test_suffixless_url_mp3_keeps_original_bytes(
    tmp_path, monkeypatch, media_server
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    _write_media(tmp_path, "song", MP3_SAMPLE)

    payload = await Record(file=f"{media_server}/song").convert_to_base64()

    assert base64.b64decode(payload) == MP3_SAMPLE


@pytest.mark.asyncio
async def test_suffixless_base64_mp3_keeps_original_bytes(tmp_path, monkeypatch):
    """Magic-byte detection must preserve MP3 even when the suffix is ``.wav``."""
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))

    payload = await Record.fromBase64(MP3_SAMPLE_BASE64).convert_to_base64()

    assert base64.b64decode(payload) == MP3_SAMPLE


@pytest.mark.asyncio
@requires_ffmpeg
async def test_preserve_mp3_does_not_override_explicit_target_format(
    tmp_path, monkeypatch
):
    """An explicit ``target_format`` keeps working and still forces WAV."""
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    source = _write_media(tmp_path, "sample.mp3", MP3_SAMPLE)

    resolved = await media_utils.MediaResolver(
        str(source), media_type="audio", default_suffix=".wav"
    ).to_base64(target_format="wav", preserve_mp3=True)
    decoded = base64.b64decode(resolved)

    assert decoded != MP3_SAMPLE
    assert decoded[:4] == b"RIFF"
    assert decoded[8:12] == b"WAVE"
