import asyncio
import os
import stat

import pytest

from astrbot.core.utils import io


class _FakeContent:
    def __init__(self, chunks: list[bytes | BaseException]):
        self._chunks = chunks

    async def read(self, _size: int) -> bytes:
        if self._chunks:
            chunk = self._chunks.pop(0)
            if isinstance(chunk, BaseException):
                raise chunk
            return chunk
        return b""


class _FakeResponse:
    def __init__(self, *, status: int, chunks: list[bytes | BaseException]):
        self.status = status
        self.headers = {
            "content-length": str(
                sum(len(chunk) for chunk in chunks if isinstance(chunk, bytes))
            )
        }
        self.content = _FakeContent(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse | Exception):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, *_args, **_kwargs):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _patch_download_session(monkeypatch, response: _FakeResponse):
    _patch_download_sessions(monkeypatch, [response])


def _patch_download_sessions(monkeypatch, responses: list[_FakeResponse | Exception]):
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(
        io.aiohttp,
        "ClientSession",
        lambda **_kwargs: _FakeSession(responses.pop(0)),
    )


@pytest.mark.asyncio
async def test_download_file_rejects_non_200_response(monkeypatch, tmp_path):
    target_path = tmp_path / "missing.bin"
    _patch_download_session(
        monkeypatch,
        _FakeResponse(status=404, chunks=[b"not found"]),
    )

    with pytest.raises(io.DownloadFileHTTPError, match="HTTP status code: 404"):
        await io.download_file("https://example.test/missing", str(target_path))

    assert not target_path.exists()


@pytest.mark.asyncio
async def test_download_file_rejects_non_200_response_after_ssl_fallback(
    monkeypatch,
    tmp_path,
):
    class FakeSSLError(Exception):
        pass

    target_path = tmp_path / "missing.bin"
    _patch_download_sessions(
        monkeypatch,
        [
            FakeSSLError(),
            _FakeResponse(status=404, chunks=[b"not found"]),
        ],
    )
    monkeypatch.setattr(io.aiohttp, "ClientConnectorSSLError", FakeSSLError)
    monkeypatch.setattr(io.aiohttp, "ClientConnectorCertificateError", FakeSSLError)

    with pytest.raises(io.DownloadFileHTTPError, match="HTTP status code: 404"):
        await io.download_file("https://example.test/missing", str(target_path))

    assert not target_path.exists()


@pytest.mark.asyncio
async def test_download_file_writes_successful_response(monkeypatch, tmp_path):
    target_path = tmp_path / "ok.bin"
    _patch_download_session(
        monkeypatch,
        _FakeResponse(status=200, chunks=[b"hello", b" world"]),
    )

    await io.download_file("https://example.test/ok.bin", str(target_path))

    assert target_path.read_bytes() == b"hello world"


@pytest.fixture(params=[False, True], ids=["verified", "ssl-fallback"])
def patch_response(request, monkeypatch):
    """Install a response on either of the downloader's TLS paths.

    Args:
        request: Pytest request selecting the TLS path.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        A callable that installs a fake response for a download.
    """

    class FakeSSLError(Exception):
        pass

    monkeypatch.setattr(io.aiohttp, "ClientConnectorSSLError", FakeSSLError)
    monkeypatch.setattr(io.aiohttp, "ClientConnectorCertificateError", FakeSSLError)

    def install(response):
        responses = [FakeSSLError(), response] if request.param else [response]
        _patch_download_sessions(monkeypatch, responses)

    return install


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True], ids=["new", "overwrite"])
@pytest.mark.parametrize(
    "error_type",
    [io.aiohttp.ClientPayloadError, TimeoutError, asyncio.CancelledError],
)
async def test_failed_download_preserves_destination_and_cleans_staging(
    patch_response, tmp_path, existing, error_type
):
    target = tmp_path / "download.bin"
    if existing:
        target.write_bytes(b"previous complete download")
    patch_response(
        _FakeResponse(status=200, chunks=[b"partial", error_type("interrupted")])
    )

    with pytest.raises(error_type, match="interrupted"):
        await io.download_file("https://example.test/file", str(target))

    if existing:
        assert target.read_bytes() == b"previous complete download"
    else:
        assert not target.exists()
    assert list(tmp_path.iterdir()) == ([target] if existing else [])


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True], ids=["new", "overwrite"])
async def test_download_publishes_only_after_all_chunks_are_received(
    patch_response, tmp_path, existing
):
    target = tmp_path / "download.bin"
    if existing:
        target.write_bytes(b"old")
    patch_response(_FakeResponse(status=200, chunks=[b"hello", b" world"]))
    progress = []

    async def on_progress(payload):
        progress.append(payload)
        if existing:
            assert target.read_bytes() == b"old"
        else:
            assert not target.exists()

    await io.download_file(
        "https://example.test/file", str(target), progress_callback=on_progress
    )

    assert target.read_bytes() == b"hello world"
    assert list(tmp_path.iterdir()) == [target]
    assert progress[0]["downloaded"] == 0
    assert progress[-1]["downloaded"] == 11
    assert progress[-1]["percent"] == 1


@pytest.mark.asyncio
async def test_download_preserves_existing_permissions(patch_response, tmp_path):
    target = tmp_path / "download.bin"
    target.write_bytes(b"old")
    target.chmod(0o600)
    original_mode = stat.S_IMODE(target.stat().st_mode)
    patch_response(_FakeResponse(status=200, chunks=[b"new"]))

    await io.download_file("https://example.test/file", str(target))

    assert target.read_bytes() == b"new"
    assert stat.S_IMODE(target.stat().st_mode) == original_mode


@pytest.mark.asyncio
async def test_download_preserves_destination_symlink(patch_response, require_symlink):
    target = require_symlink / "target.bin"
    target.write_bytes(b"old")
    link = require_symlink / "download.bin"
    link.symlink_to(target)
    patch_response(_FakeResponse(status=200, chunks=[b"new"]))

    await io.download_file("https://example.test/file", str(link))

    assert link.is_symlink()
    assert target.read_bytes() == b"new"
    assert set(require_symlink.iterdir()) == {target, link}


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True], ids=["disconnect", "cancel"])
async def test_interrupted_http_download_cannot_clobber_concurrent_success(
    tmp_path, monkeypatch, cancelled
):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    target = tmp_path / "download.bin"
    target.write_bytes(b"old")
    partial_received = asyncio.Event()
    release_connection = asyncio.Event()
    handlers = []

    async def handle_connection(reader, writer):
        handlers.append(asyncio.current_task())
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\n")
            if request.startswith(b"GET /interrupted "):
                writer.write(b"part")
                await writer.drain()
                await release_connection.wait()
            else:
                writer.write(b"complete!")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    def on_progress(payload):
        if payload["downloaded"]:
            partial_received.set()

    server = await asyncio.start_server(handle_connection, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        pending = asyncio.create_task(
            io.download_file(
                f"http://127.0.0.1:{port}/interrupted",
                str(target),
                progress_callback=on_progress,
            )
        )
        try:
            await asyncio.wait_for(partial_received.wait(), timeout=10)
            assert target.read_bytes() == b"old"
            await io.download_file(f"http://127.0.0.1:{port}/complete", str(target))
            assert target.read_bytes() == b"complete!"
            if cancelled:
                pending.cancel()
            else:
                release_connection.set()
            error_type = (
                asyncio.CancelledError if cancelled else io.aiohttp.ClientPayloadError
            )
            with pytest.raises(error_type):
                await asyncio.wait_for(pending, timeout=10)
        finally:
            release_connection.set()
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            await asyncio.gather(*handlers)

    assert target.read_bytes() == b"complete!"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.asyncio
async def test_callback_failure_does_not_publish_download(patch_response, tmp_path):
    target = tmp_path / "download.bin"
    target.write_bytes(b"old")
    patch_response(_FakeResponse(status=200, chunks=[b"new"]))

    def on_progress(payload):
        if payload["downloaded"]:
            raise RuntimeError("progress callback failed")

    with pytest.raises(RuntimeError, match="progress callback failed"):
        await io.download_file(
            "https://example.test/file", str(target), progress_callback=on_progress
        )

    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.asyncio
async def test_failed_publication_preserves_destination(
    patch_response, tmp_path, monkeypatch
):
    target = tmp_path / "download.bin"
    target.write_bytes(b"old")
    patch_response(_FakeResponse(status=200, chunks=[b"new"]))

    def fail_replace(staging, destination, original_stat):
        raise PermissionError("destination is busy")

    monkeypatch.setattr(io, "_publish_download", fail_replace)
    with pytest.raises(PermissionError, match="destination is busy"):
        await io.download_file("https://example.test/file", str(target))

    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.asyncio
@pytest.mark.skipif(os.name == "nt", reason="POSIX mode and xattrs")
async def test_download_preserves_access_metadata_without_privilege_bits(
    patch_response, tmp_path
):
    target = tmp_path / "download.bin"
    target.write_bytes(b"old")
    target.chmod(0o6750)
    before = target.stat()
    if hasattr(os, "setxattr"):
        os.setxattr(target, "user.astrbot-test", b"keep this metadata")
    patch_response(_FakeResponse(status=200, chunks=[b"new"]))

    await io.download_file("https://example.test/file", str(target))

    assert target.read_bytes() == b"new"
    assert stat.S_IMODE(target.stat().st_mode) == 0o750
    assert (target.stat().st_uid, target.stat().st_gid) == (before.st_uid, before.st_gid)
    if hasattr(os, "getxattr"):
        assert os.getxattr(target, "user.astrbot-test") == b"keep this metadata"


@pytest.mark.asyncio
async def test_readonly_destination_is_not_overwritten(patch_response, tmp_path):
    if os.name != "nt" and os.geteuid() == 0:
        pytest.skip("Root bypasses ordinary file write permissions")
    target = tmp_path / "download.bin"
    target.write_bytes(b"old")
    target.chmod(0o444)
    patch_response(_FakeResponse(status=200, chunks=[b"new"]))
    try:
        with pytest.raises(PermissionError):
            await io.download_file("https://example.test/file", str(target))
        assert target.read_bytes() == b"old"
        assert list(tmp_path.iterdir()) == [target]
    finally:
        target.chmod(0o600)


@pytest.mark.asyncio
async def test_older_success_cannot_replace_newer_download(monkeypatch, tmp_path):
    target = tmp_path / "download.bin"
    target.write_bytes(b"old")
    older_ready = asyncio.Event()
    release_older = asyncio.Event()
    _patch_download_sessions(monkeypatch, [
        _FakeResponse(status=200, chunks=[b"older response"]),
        _FakeResponse(status=200, chunks=[b"newer response"]),
    ])

    async def older_progress(payload):
        if payload["downloaded"]:
            older_ready.set()
            await release_older.wait()

    pending = asyncio.create_task(io.download_file(
        "https://example.test/older", str(target), progress_callback=older_progress
    ))
    try:
        await asyncio.wait_for(older_ready.wait(), 5)
        await io.download_file("https://example.test/newer", str(target))
        release_older.set()
        with pytest.raises(FileExistsError, match="changed while downloading"):
            await pending
        assert target.read_bytes() == b"newer response"
        assert list(tmp_path.iterdir()) == [target]
    finally:
        release_older.set()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="Windows alternate data streams")
async def test_windows_replacement_preserves_alternate_stream(patch_response, tmp_path):
    target = tmp_path / "download.bin"
    target.write_bytes(b"old")
    stream = io.Path(str(target) + ":astrbot-test")
    stream.write_bytes(b"existing access metadata")
    patch_response(_FakeResponse(status=200, chunks=[b"new"]))

    await io.download_file("https://example.test/file", str(target))

    assert target.read_bytes() == b"new"
    assert stream.read_bytes() == b"existing access metadata"


@pytest.mark.asyncio
@pytest.mark.skipif(os.name == "nt", reason="POSIX directory permissions")
async def test_nonwritable_parent_fails_without_changing_existing_file(
    patch_response, tmp_path
):
    if os.geteuid() == 0:
        pytest.skip("Root bypasses ordinary directory write permissions")
    folder = tmp_path / "protected"
    folder.mkdir()
    target = folder / "download.bin"
    target.write_bytes(b"old")
    folder.chmod(0o555)
    patch_response(_FakeResponse(status=200, chunks=[b"new"]))
    try:
        with pytest.raises(PermissionError):
            await io.download_file("https://example.test/file", str(target))
        assert target.read_bytes() == b"old"
    finally:
        folder.chmod(0o755)
