import pytest
from aiohttp import web

from astrbot.core.utils import io as io_module
from astrbot.core.utils.io import _stream_to_file, download_file
from tests.fixtures.helpers import get_bound_tcp_port


@pytest.mark.asyncio
async def test_download_file_downloads_content(tmp_path):
    payload = b"astrbot-download-payload" * 256

    async def handle(_request):
        return web.Response(body=payload)

    app = web.Application()
    app.router.add_get("/file.bin", handle)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    try:
        port = get_bound_tcp_port(site)
        url = f"http://127.0.0.1:{port}/file.bin"

        out = tmp_path / "downloaded.bin"
        await download_file(url, str(out))

        assert out.read_bytes() == payload
    finally:
        await runner.cleanup()


class _DummyStream:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def read(self, _size: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class _RecordingFile:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)


@pytest.mark.asyncio
async def test_stream_to_file_batches_multiple_chunks_per_write(monkeypatch):
    monkeypatch.setattr(io_module, "_DOWNLOAD_READ_CHUNK_SIZE", 4)
    monkeypatch.setattr(io_module, "_DOWNLOAD_FLUSH_THRESHOLD", 10)

    stream = _DummyStream([b"aaaa", b"bbbb", b"cccc"])
    file_obj = _RecordingFile()

    await _stream_to_file(
        stream,
        file_obj,
        total_size=12,
        start_time=0.0,
        show_progress=False,
    )

    assert len(file_obj.writes) == 1
    assert file_obj.writes[0] == b"aaaabbbbcccc"
