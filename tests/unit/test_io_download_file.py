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


class _FakeImageResponse:
    def __init__(
        self,
        *,
        status: int,
        body: bytes,
        content_type: str = "image/jpeg",
    ) -> None:
        self.status = status
        self._body = body
        self.headers = {"Content-Type": content_type}

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _RecordingImageSession:
    def __init__(
        self,
        responses: list[_FakeImageResponse | Exception],
        recorded_calls: list[dict],
        session_kwargs: dict,
    ) -> None:
        self._responses = responses
        self._recorded_calls = recorded_calls
        self._session_kwargs = session_kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def _dispatch(self, method: str, url: str, **kwargs):
        self._recorded_calls.append(
            {
                "method": method,
                "url": url,
                "session_kwargs": self._session_kwargs,
                "request_kwargs": kwargs,
            }
        )
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item

    def get(self, url: str, **kwargs):
        return self._dispatch("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self._dispatch("POST", url, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "content_type", "body"),
    [
        (502, "text/html", b"bad gateway"),
        (200, "application/json", b'{"error": "render failed"}'),
        (200, "image/jpeg", b""),
    ],
)
async def test_download_image_by_url_rejects_error_or_empty_responses(
    monkeypatch, tmp_path, status, content_type, body
):
    recorded: list[dict] = []
    responses: list[_FakeImageResponse | Exception] = [
        _FakeImageResponse(status=status, body=body, content_type=content_type)
    ]
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(
        io.aiohttp,
        "ClientSession",
        lambda **kwargs: _RecordingImageSession(responses, recorded, kwargs),
    )

    target_path = tmp_path / "out.jpg"
    with pytest.raises(io.DownloadFileHTTPError):
        await io.download_image_by_url(
            "https://example.test/render",
            post=True,
            post_data={"tmpl": "hi"},
            path=str(target_path),
            timeout=12,
        )

    assert not target_path.exists()
    assert recorded[0]["session_kwargs"].get("trust_env") is True
    assert recorded[0]["request_kwargs"]["timeout"].total == 12


@pytest.mark.asyncio
async def test_download_image_by_url_ssl_fallback_keeps_trust_env_and_timeout(
    monkeypatch, tmp_path
):
    class FakeSSLError(Exception):
        pass

    recorded: list[dict] = []
    responses: list[_FakeImageResponse | Exception] = [
        FakeSSLError(),
        _FakeImageResponse(status=200, body=b"jpeg-bytes", content_type="image/jpeg"),
    ]
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(io.aiohttp, "ClientConnectorSSLError", FakeSSLError)
    monkeypatch.setattr(io.aiohttp, "ClientConnectorCertificateError", FakeSSLError)
    monkeypatch.setattr(
        io.aiohttp,
        "ClientSession",
        lambda **kwargs: _RecordingImageSession(responses, recorded, kwargs),
    )

    target_path = tmp_path / "fallback.jpg"
    result = await io.download_image_by_url(
        "https://example.test/image.jpg",
        path=str(target_path),
        timeout=18,
    )

    assert result == str(target_path)
    assert target_path.read_bytes() == b"jpeg-bytes"
    assert len(recorded) == 2
    assert recorded[1]["session_kwargs"].get("trust_env") is True
    assert recorded[1]["request_kwargs"]["timeout"].total == 18


@pytest.mark.asyncio
async def test_network_render_strategy_fails_over_on_http_error(monkeypatch, tmp_path):
    from astrbot.core.utils.t2i import network_strategy

    recorded_urls: list[str] = []
    responses: list[_FakeImageResponse | Exception] = [
        _FakeImageResponse(status=502, body=b"bad gateway", content_type="text/plain"),
        _FakeImageResponse(status=200, body=b"valid-img", content_type="image/jpeg"),
    ]
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(
        io.aiohttp,
        "ClientSession",
        lambda **kwargs: _RecordingImageSession(
            responses,
            [],
            kwargs,
        ),
    )

    orig_fetch = io._fetch_image_bytes

    async def recording_fetch(session, url, **kwargs):
        recorded_urls.append(url)
        return await orig_fetch(session, url, **kwargs)

    monkeypatch.setattr(io, "_fetch_image_bytes", recording_fetch)
    monkeypatch.setattr(
        io, "save_temp_img", lambda data: str(tmp_path / f"img_{len(data)}.jpg")
    )

    strategy = network_strategy.NetworkRenderStrategy()
    strategy.endpoints = ["https://bad.t2i/text2img", "https://good.t2i/text2img"]
    monkeypatch.setattr(network_strategy.random, "shuffle", lambda items: None)

    out = await strategy.render_custom_template(
        "{{ text }}", {"text": "hi"}, return_url=False
    )
    assert out == str(tmp_path / f"img_{len(b'valid-img')}.jpg")
    assert recorded_urls == [
        "https://bad.t2i/text2img/generate",
        "https://good.t2i/text2img/generate",
    ]
