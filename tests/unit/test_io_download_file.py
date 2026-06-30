import pytest

from astrbot.core.utils import io


class _FakeContent:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def read(self, _size: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class _FakeResponse:
    def __init__(self, *, status: int, chunks: list[bytes]):
        self.status = status
        self.headers = {"content-length": str(sum(len(chunk) for chunk in chunks))}
        self.content = _FakeContent(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, *_args, **_kwargs):
        return self._response


def _patch_download_session(monkeypatch, response: _FakeResponse):
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(
        io.aiohttp,
        "ClientSession",
        lambda **_kwargs: _FakeSession(response),
    )


@pytest.mark.asyncio
async def test_download_file_rejects_non_200_response(monkeypatch, tmp_path):
    target_path = tmp_path / "missing.bin"
    _patch_download_session(
        monkeypatch,
        _FakeResponse(status=404, chunks=[b"not found"]),
    )

    with pytest.raises(RuntimeError, match="HTTP status code: 404"):
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
