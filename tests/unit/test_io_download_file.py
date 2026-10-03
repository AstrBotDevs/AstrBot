import asyncio
import socket

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
    def __init__(
        self,
        *,
        status: int,
        chunks: list[bytes],
        headers: dict[str, str] | None = None,
    ):
        self.status = status
        self.headers = {
            "content-length": str(sum(len(chunk) for chunk in chunks)),
            **(headers or {}),
        }
        self._body = b"".join(chunks)
        self.content = _FakeContent(chunks.copy())

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse | Exception):
        self._response = response
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, *_args, **_kwargs):
        self.calls.append(("GET", _kwargs))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    def post(self, *_args, **_kwargs):
        self.calls.append(("POST", _kwargs))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _public_resolution(hostname: str = "example.test") -> tuple[str, list[dict]]:
    return hostname, [
        {
            "hostname": hostname,
            "host": "93.184.216.34",
            "port": 443,
            "family": socket.AF_INET,
            "proto": socket.IPPROTO_TCP,
            "flags": socket.AI_NUMERICHOST,
        }
    ]


def _public_dns_result() -> list[tuple]:
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        )
    ]


async def _fake_public_resolver(
    _url: str,
    _allow_private_network: bool,
    _allowed_origin=None,
) -> tuple[str, list[dict]]:
    return _public_resolution()


def _patch_download_session(monkeypatch, response: _FakeResponse):
    _patch_download_sessions(monkeypatch, [response])


def _patch_download_sessions(monkeypatch, responses: list[_FakeResponse | Exception]):
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(io, "_resolve_and_validate_url", _fake_public_resolver)
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://10.0.0.1/metadata",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/admin",
        "http://[fd00::1]/admin",
    ],
)
async def test_download_file_rejects_private_network_targets(url, tmp_path):
    with pytest.raises(io.SSRFProtectionError, match="non-public address"):
        await io.download_file(url, str(tmp_path / "blocked.bin"))


@pytest.mark.asyncio
async def test_resolve_and_validate_url_rejects_private_dns_result(monkeypatch):
    class FakeLoop:
        async def getaddrinfo(self, *_args, **_kwargs):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("192.168.1.10", 80),
                )
            ]

    monkeypatch.setattr(io.asyncio, "get_running_loop", lambda: FakeLoop())

    with pytest.raises(io.SSRFProtectionError, match="non-public address"):
        await io._resolve_and_validate_url("http://assets.example.test/file", False)


@pytest.mark.asyncio
async def test_pinned_resolver_returns_validated_addresses():
    resolver = io._PinnedResolver()
    resolver.pin(*_public_resolution())

    try:
        addresses = await resolver.resolve("example.test", 443, socket.AF_UNSPEC)
    finally:
        await resolver.close()

    assert addresses[0]["host"] == "93.184.216.34"


@pytest.mark.asyncio
async def test_pinned_resolver_uses_yarl_idna_hostname(monkeypatch):
    class FakeLoop:
        async def getaddrinfo(self, *_args, **_kwargs):
            return _public_dns_result()

    monkeypatch.setattr(io.asyncio, "get_running_loop", lambda: FakeLoop())
    hostname, addresses_to_pin = await io._resolve_and_validate_url(
        "https://faß.de/file", True
    )
    assert hostname == io.URL("https://faß.de").raw_host == "xn--fa-hia.de"

    resolver = io._PinnedResolver()
    resolver.pin(hostname, addresses_to_pin)

    try:
        addresses = await resolver.resolve(
            "xn--fa-hia.de",
            443,
            socket.AF_UNSPEC,
        )
        with pytest.raises(io.SSRFProtectionError, match="unvalidated hostname"):
            await resolver.resolve("other.example", 443, socket.AF_UNSPEC)
    finally:
        await resolver.close()

    assert addresses[0]["host"] == "93.184.216.34"


@pytest.mark.asyncio
async def test_resolve_and_validate_url_rejects_untrusted_origin(monkeypatch):
    class FakeLoop:
        async def getaddrinfo(self, *_args, **_kwargs):
            return _public_dns_result()

    monkeypatch.setattr(io.asyncio, "get_running_loop", lambda: FakeLoop())

    with pytest.raises(io.SSRFProtectionError, match="not the trusted origin"):
        await io._resolve_and_validate_url(
            "https://other.example/file",
            False,
            io.URL("https://example.test").origin(),
        )


@pytest.mark.asyncio
async def test_download_file_does_not_use_environment_proxy(monkeypatch, tmp_path):
    response = _FakeResponse(status=200, chunks=[b"payload"])
    session_options: dict = {}

    def fake_session(**kwargs):
        session_options.update(kwargs)
        return _FakeSession(response)

    monkeypatch.setattr(io, "_resolve_and_validate_url", _fake_public_resolver)
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(io.aiohttp, "ClientSession", fake_session)

    await io.download_file("https://example.test/file", str(tmp_path / "file"))

    assert session_options["trust_env"] is False


@pytest.mark.asyncio
async def test_download_file_rejects_cross_origin_redirect(monkeypatch, tmp_path):
    response = _FakeResponse(
        status=302,
        chunks=[],
        headers={"Location": "https://other.example/admin"},
    )
    sessions: list[_FakeSession] = []

    class FakeLoop:
        async def getaddrinfo(self, *_args, **_kwargs):
            return _public_dns_result()

    def fake_session(**_kwargs):
        session = _FakeSession(response)
        sessions.append(session)
        return session

    monkeypatch.setattr(io.asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(io.aiohttp, "ClientSession", fake_session)

    with pytest.raises(io.SSRFProtectionError, match="not the trusted origin"):
        await io.download_file(
            "https://example.test/file",
            str(tmp_path / "file"),
            allow_private_network=True,
            allowed_origin="https://example.test",
        )

    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_download_file_validates_redirect_target(monkeypatch, tmp_path):
    target_path = tmp_path / "blocked.bin"
    response = _FakeResponse(
        status=302,
        chunks=[],
        headers={"Location": "http://127.0.0.1/admin"},
    )
    sessions: list[_FakeSession] = []

    async def fake_resolve(
        url: str, _allow_private_network: bool, _allowed_origin=None
    ):
        if "127.0.0.1" in url:
            raise io.SSRFProtectionError("non-public address 127.0.0.1 is blocked")
        return _public_resolution("public.example.test")

    def fake_session(**_kwargs):
        session = _FakeSession(response)
        sessions.append(session)
        return session

    monkeypatch.setattr(io, "_resolve_and_validate_url", fake_resolve)
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(io.aiohttp, "ClientSession", fake_session)

    with pytest.raises(io.SSRFProtectionError, match="non-public address"):
        await io.download_file("https://public.example.test/file", str(target_path))

    assert len(sessions) == 1
    assert not target_path.exists()


@pytest.mark.asyncio
async def test_download_image_by_url_supports_post_with_validation(
    monkeypatch, tmp_path
):
    response = _FakeResponse(status=200, chunks=[b"image"])
    sessions: list[_FakeSession] = []

    def fake_session(**_kwargs):
        session = _FakeSession(response)
        sessions.append(session)
        return session

    monkeypatch.setattr(io, "_resolve_and_validate_url", _fake_public_resolver)
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **_kwargs: object())
    monkeypatch.setattr(io.aiohttp, "ClientSession", fake_session)

    output_path = tmp_path / "image.bin"
    result = await io.download_image_by_url(
        "https://example.test/render",
        post=True,
        post_data={"text": "hello"},
        path=str(output_path),
    )

    assert result == str(output_path)
    assert output_path.read_bytes() == b"image"
    assert sessions[0].calls[0][0] == "POST"


@pytest.mark.asyncio
async def test_download_file_uses_pinned_dns_with_real_aiohttp_connector(
    monkeypatch, tmp_path
):
    async def serve_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            if request.startswith(b"GET /redirect "):
                writer.write(
                    b"HTTP/1.1 302 Found\r\n"
                    b"Location: /payload\r\n"
                    b"Content-Length: 0\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                )
            else:
                writer.write(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Length: 7\r\n"
                    b"Connection: close\r\n"
                    b"\r\npayload"
                )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(serve_file, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    target_path = tmp_path / "payload.bin"
    hostname = "pinned-dns.test"
    resolution_calls: list[tuple[str, int]] = []

    async def fake_getaddrinfo(
        _loop: asyncio.AbstractEventLoop,
        host: str,
        requested_port: int,
        *_args,
        **_kwargs,
    ) -> list[tuple]:
        resolution_calls.append((host, requested_port))
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", port),
            )
        ]

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(type(loop), "getaddrinfo", fake_getaddrinfo)

    url = f"http://{hostname}:{port}/redirect"
    try:
        await io.download_file(
            url,
            str(target_path),
            allow_private_network=True,
            allowed_origin=f"http://{hostname}:{port}",
        )
    finally:
        server.close()
        await server.wait_closed()

    assert target_path.read_bytes() == b"payload"
    # The redirect is validated separately; the connector must not resolve the
    # hostname again while opening either connection.
    assert resolution_calls == [(hostname, port), (hostname, port)]
