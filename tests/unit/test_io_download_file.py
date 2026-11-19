import pytest
from aiohttp import web
from aiohttp.http import SERVER_SOFTWARE

from astrbot.core.utils import io, media_utils


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

    async def read(self) -> bytes:
        return await self.content.read(-1)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse | Exception, requests):
        self._response = response
        self._requests = requests

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, *_args, **kwargs):
        self._requests.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _patch_download_session(monkeypatch, response: _FakeResponse):
    _patch_download_sessions(monkeypatch, [response])


def _patch_download_sessions(monkeypatch, responses: list[_FakeResponse | Exception]):
    requests = []
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(
        io.aiohttp,
        "ClientSession",
        lambda **_kwargs: _FakeSession(responses.pop(0), requests),
    )
    return requests


@pytest.mark.asyncio
@pytest.mark.parametrize("ssl_fallback", [False, True])
async def test_download_file_rejects_non_200_response(
    monkeypatch, tmp_path, ssl_fallback
):
    class FakeSSLError(Exception):
        pass

    target_path = tmp_path / "missing.bin"
    response = _FakeResponse(status=404, chunks=[b"not found"])
    if ssl_fallback:
        _patch_download_sessions(monkeypatch, [FakeSSLError(), response])
        monkeypatch.setattr(io.aiohttp, "ClientConnectorSSLError", FakeSSLError)
        monkeypatch.setattr(io.aiohttp, "ClientConnectorCertificateError", FakeSSLError)
    else:
        _patch_download_session(monkeypatch, response)

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


@pytest.mark.asyncio
@pytest.mark.parametrize("download", [io.download_file, io.download_image_by_url])
@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [(None, io.DOWNLOAD_USER_AGENT), ("Caller/1", "Caller/1")],
)
async def test_download_get_user_agent_is_preserved_on_tls_retry(
    monkeypatch, tmp_path, download, user_agent, expected
):
    class FakeSSLError(Exception):
        pass

    monkeypatch.setattr(io.aiohttp, "ClientConnectorSSLError", FakeSSLError)
    requests = _patch_download_sessions(
        monkeypatch, [FakeSSLError(), _FakeResponse(status=200, chunks=[b"data"])]
    )
    target = tmp_path / "result.bin"

    await download("https://example.test/file", path=str(target), user_agent=user_agent)

    assert target.read_bytes() == b"data"
    assert len(requests) == 2
    for kwargs in requests:
        assert kwargs["headers"] == {"User-Agent": expected}


@pytest.mark.asyncio
async def test_download_get_and_media_wire_headers_do_not_change_generation_post(
    tmp_path, monkeypatch
):
    seen = []

    async def endpoint(request):
        seen.append(
            (
                request.method,
                request.headers.getall("User-Agent"),
            )
        )
        return web.Response(body=b"downloaded")

    app = web.Application()
    app.router.add_route("*", "/file.png", endpoint)
    runner = web.AppRunner(app)
    await runner.setup()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    try:
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        url = f"http://127.0.0.1:{runner.addresses[0][1]}/file.png"
        await io.download_file(url, str(tmp_path / "file.bin"))
        await io.download_image_by_url(
            url, path=str(tmp_path / "image.bin"), user_agent="Caller/1"
        )
        await io.download_image_by_url(
            url,
            post=True,
            post_data={"x": 1},
            path=str(tmp_path / "generated.bin"),
            user_agent="ignored-for-post",
        )
        async with media_utils.MediaResolver(
            url, media_type="image"
        ).as_path() as media:
            assert media.read_bytes() == b"downloaded"
    finally:
        await runner.cleanup()

    assert seen == [
        ("GET", [io.DOWNLOAD_USER_AGENT]),
        ("GET", ["Caller/1"]),
        ("POST", [SERVER_SOFTWARE]),
        ("GET", [io.DOWNLOAD_USER_AGENT]),
    ]
