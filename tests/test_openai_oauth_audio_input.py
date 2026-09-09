import asyncio
import base64
import io
import shutil
import tempfile
import wave
from pathlib import Path

import httpx
import pytest

import astrbot.core.provider.oauth.openai_oauth_audio_input as audio_input
from astrbot.core.provider.oauth.openai_oauth_audio_input import (
    BoundedOAuthAudioResolver,
)


def _write_wav(path: Path, frames: int = 1) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\x00\x00" * frames)


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks, wait_after_first: asyncio.Event | None = None):
        self.chunks = chunks
        self.wait_after_first = wait_after_first
        self.closed = False

    async def __aiter__(self):
        for index, chunk in enumerate(self.chunks):
            yield chunk
            if index == 0 and self.wait_after_first is not None:
                await self.wait_after_first.wait()

    async def aclose(self):
        self.closed = True


def _install_transport(monkeypatch, stream, headers=None, status_code=200):
    original_client = httpx.AsyncClient

    async def handler(request):
        assert str(request.url) == "https://example.test/voice"
        return httpx.Response(status_code, headers=headers or {}, stream=stream)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        audio_input.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=transport,
            timeout=kwargs.get("timeout"),
            follow_redirects=kwargs.get("follow_redirects", False),
        ),
    )


@pytest.mark.asyncio
async def test_local_wav_and_base64_wav_resolve_with_owned_cleanup(tmp_path):
    source = tmp_path / "voice.wav"
    _write_wav(source, frames=4)
    source_bytes = source.read_bytes()

    for reference in (
        str(source),
        "data:audio/wav;base64," + base64.b64encode(source_bytes).decode(),
        "base64://" + base64.b64encode(source_bytes).decode(),
        "base64://" + base64.b64encode(source_bytes).decode().rstrip("="),
    ):
        resolver = BoundedOAuthAudioResolver(
            reference,
            max_bytes=4096,
            timeout=2,
        )
        async with resolver.as_wav_path() as resolved:
            resolved_path = resolved.path
            assert resolved.path.read_bytes() == source_bytes
            assert resolved.mime_type == "audio/wav"
        assert resolved_path.exists() is False


@pytest.mark.asyncio
async def test_chunked_download_without_content_length_stops_at_limit_and_cleans(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    stream = _ChunkStream([b"RIFF1234", b"56789"])
    _install_transport(monkeypatch, stream)
    resolver = BoundedOAuthAudioResolver(
        "https://example.test/voice",
        max_bytes=10,
        timeout=2,
    )

    with pytest.raises(ValueError, match="大小上限"):
        async with resolver.as_wav_path():
            pass

    assert stream.closed is True
    assert list(tmp_path.glob("astrbot_oauth_audio_*")) == []


@pytest.mark.asyncio
async def test_http_wav_download_resolves_normally(tmp_path, monkeypatch):
    sample = tmp_path / "sample.wav"
    _write_wav(sample, frames=4)
    stream = _ChunkStream([sample.read_bytes()])
    _install_transport(monkeypatch, stream)
    resolver = BoundedOAuthAudioResolver(
        "https://example.test/voice",
        max_bytes=4096,
        timeout=2,
    )

    async with resolver.as_wav_path() as resolved:
        assert resolved.path.name == "normalized.wav"
        assert resolved.path.read_bytes() == sample.read_bytes()

    assert stream.closed is True


@pytest.mark.asyncio
async def test_content_length_is_rejected_before_streaming(monkeypatch):
    stream = _ChunkStream([b"RIFF" + b"x" * 100])
    _install_transport(monkeypatch, stream, headers={"content-length": "104"})
    resolver = BoundedOAuthAudioResolver(
        "https://example.test/voice",
        max_bytes=64,
        timeout=2,
    )

    with pytest.raises(ValueError, match="大小上限"):
        async with resolver.as_wav_path():
            pass

    assert stream.closed is True


def test_long_signed_url_preserves_bounded_path_filename():
    resolver = BoundedOAuthAudioResolver(
        "https://example.test/media/voice.m4a?signature=" + "x" * 500,
        max_bytes=4096,
        timeout=2,
    )

    assert resolver._source_filename() == "voice.m4a"


@pytest.mark.asyncio
async def test_http_error_does_not_expose_signed_url(monkeypatch):
    secret_url = "https://example.test/voice?signature=private-value"
    stream = _ChunkStream([])
    original_client = httpx.AsyncClient

    async def handler(_request):
        return httpx.Response(404, stream=stream)

    monkeypatch.setattr(
        audio_input.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler),
            timeout=kwargs.get("timeout"),
            follow_redirects=True,
        ),
    )
    resolver = BoundedOAuthAudioResolver(secret_url, max_bytes=4096, timeout=2)

    with pytest.raises(ValueError) as exc_info:
        async with resolver.as_wav_path():
            pass

    assert "HTTP 404" in str(exc_info.value)
    assert "private-value" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"#!AMR\n" + b"x" * 26, "amr"),
        (b"\x00\x00\x00\x18ftypM4A " + b"x" * 20, "m4a"),
        (b"\xff\xf1" + b"x" * 30, "aac"),
    ],
)
async def test_extensionless_compressed_audio_magic_is_detected(
    tmp_path,
    header,
    expected,
):
    source = tmp_path / "audio"
    source.write_bytes(header)
    resolver = BoundedOAuthAudioResolver(str(source), max_bytes=4096, timeout=2)

    assert await resolver._detect_format(source) == expected


@pytest.mark.asyncio
async def test_download_cancellation_closes_stream_and_removes_partial_file(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    release = asyncio.Event()
    stream = _ChunkStream([b"RIFF1234", b"5678"], wait_after_first=release)
    _install_transport(monkeypatch, stream)
    resolver = BoundedOAuthAudioResolver(
        "https://example.test/voice",
        max_bytes=4096,
        timeout=10,
    )

    async def consume():
        async with resolver.as_wav_path():
            raise AssertionError("download should still be waiting")

    task = asyncio.create_task(consume())
    for _ in range(100):
        if list(tmp_path.glob("astrbot_oauth_audio_*/input.bin")):
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()

    assert stream.closed is True
    assert list(tmp_path.glob("astrbot_oauth_audio_*")) == []


@pytest.mark.asyncio
async def test_conversion_cancellation_kills_and_waits_for_owned_process(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    source = tmp_path / "voice.mp3"
    source.write_bytes(b"ID3" + b"\x00" * 32)
    started = asyncio.Event()

    class FakeProcess:
        returncode = None
        killed = False
        waited = False

        async def communicate(self):
            started.set()
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            self.waited = True
            return self.returncode

    process = FakeProcess()
    process_calls = []

    async def create_process(*args, **kwargs):
        process_calls.append((args, kwargs))
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    resolver = BoundedOAuthAudioResolver(str(source), max_bytes=4096, timeout=10)

    async def consume():
        async with resolver.as_wav_path():
            raise AssertionError("conversion should still be waiting")

    task = asyncio.create_task(consume())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed is True
    assert process.waited is True
    assert "preexec_fn" not in process_calls[0][1]
    if audio_input.os.name == "posix":
        assert process_calls[0][0][0] == audio_input.sys.executable
        assert process_calls[0][0][1:3] == ("-c", audio_input._LIMITED_EXEC_SCRIPT)
    assert list(tmp_path.glob("astrbot_oauth_audio_*")) == []


@pytest.mark.asyncio
async def test_decoded_output_expansion_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / "voice.mp3"
    source.write_bytes(b"ID3small")
    resolver = BoundedOAuthAudioResolver(str(source), max_bytes=64, timeout=2)

    async def expanding_conversion(_source, destination):
        destination.write_bytes(b"x" * 65)

    monkeypatch.setattr(resolver, "_convert_to_wav", expanding_conversion)

    with pytest.raises(ValueError, match="解码后音频.*大小上限"):
        async with resolver.as_wav_path():
            pass


@pytest.mark.asyncio
async def test_real_ffmpeg_ogg_conversion_produces_bounded_wav(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    source_wav = tmp_path / "source.wav"
    source_ogg = tmp_path / "source.ogg"
    _write_wav(source_wav, frames=1600)
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-i",
        str(source_wav),
        str(source_ogg),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
    resolver = BoundedOAuthAudioResolver(
        str(source_ogg),
        max_bytes=512 * 1024,
        timeout=5,
    )

    async with resolver.as_wav_path() as resolved:
        with wave.open(str(resolved.path), "rb") as decoded:
            assert decoded.getnchannels() == 1
            assert decoded.getsampwidth() == 2
            assert decoded.getframerate() == 16000
            assert decoded.getnframes() > 0


@pytest.mark.asyncio
async def test_tencent_silk_uses_bounded_decoder_path(tmp_path, monkeypatch):
    source = tmp_path / "voice.silk"
    source.write_bytes(b"\x02#!SILK_V3" + b"payload")
    resolver = BoundedOAuthAudioResolver(str(source), max_bytes=4096, timeout=2)
    calls = []

    async def fake_decode(input_path, output_path):
        calls.append((input_path.read_bytes(), output_path.name))
        _write_wav(output_path)

    monkeypatch.setattr(resolver, "_decode_silk", fake_decode)

    async with resolver.as_wav_path() as resolved:
        assert resolved.path.read_bytes().startswith(b"RIFF")

    assert calls == [(source.read_bytes(), "decoded.wav")]


@pytest.mark.asyncio
async def test_tencent_silk_is_decoded_in_bounded_child_process(tmp_path):
    import pysilk

    encoded = io.BytesIO()
    pysilk.encode(
        io.BytesIO(b"\x00\x00" * 2400),
        encoded,
        24000,
        24000,
        tencent=True,
    )
    source = tmp_path / "voice.silk"
    source.write_bytes(encoded.getvalue())
    resolver = BoundedOAuthAudioResolver(
        str(source),
        max_bytes=512 * 1024,
        timeout=5,
    )

    async with resolver.as_wav_path() as resolved:
        with wave.open(str(resolved.path), "rb") as decoded:
            assert decoded.getnchannels() == 1
            assert decoded.getsampwidth() == 2
            assert decoded.getframerate() == 24000
            assert decoded.getnframes() > 0


@pytest.mark.asyncio
async def test_unknown_audio_format_is_rejected(tmp_path):
    source = tmp_path / "voice.bin"
    source.write_bytes(b"not an audio file")
    resolver = BoundedOAuthAudioResolver(str(source), max_bytes=4096, timeout=2)

    with pytest.raises(ValueError, match="无法识别"):
        async with resolver.as_wav_path():
            pass
