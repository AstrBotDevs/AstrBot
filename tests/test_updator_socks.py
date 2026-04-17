from pathlib import Path
from types import SimpleNamespace

import certifi
import httpx
import pytest

from astrbot.core.zip_updator import RepoZipUpdator


class _FakeJSONResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeStreamResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self, chunk_size: int = 8192):
        for start in range(0, len(self._payload), chunk_size):
            yield self._payload[start : start + chunk_size]


class _FakeFailingStreamResponse:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self, chunk_size: int = 8192):  # noqa: ARG002
        yield b"partial"
        raise RuntimeError("stream interrupted")


class _FakeStatusErrorResponse:
    def __init__(self, status_code: int, body: str, url: str):
        self._status_code = status_code
        self._body = body
        self._url = url

    def raise_for_status(self) -> None:
        request = httpx.Request("GET", self._url)
        response = httpx.Response(
            self._status_code,
            text=self._body,
            request=request,
        )
        raise httpx.HTTPStatusError(
            "status error",
            request=request,
            response=response,
        )


class _FakeAsyncClient:
    init_kwargs: dict | None = None
    requested_urls: list[str] = []
    stream_urls: list[str] = []
    json_payload = []
    stream_payload = b""

    def __init__(self, **kwargs):
        type(self).init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str):
        type(self).requested_urls.append(url)
        return _FakeJSONResponse(type(self).json_payload)

    def stream(self, method: str, url: str):
        assert method == "GET"
        type(self).stream_urls.append(url)
        return _FakeStreamResponse(type(self).stream_payload)


class _FakeStatusErrorAsyncClient:
    def __init__(self, response: _FakeStatusErrorResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str):
        return self._response


class _FakeFailingStreamAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def stream(self, method: str, url: str):  # noqa: ARG002
        return _FakeFailingStreamResponse()


def _reset_fake_client() -> None:
    _FakeAsyncClient.init_kwargs = None
    _FakeAsyncClient.requested_urls = []
    _FakeAsyncClient.stream_urls = []
    _FakeAsyncClient.json_payload = []
    _FakeAsyncClient.stream_payload = b""


@pytest.mark.asyncio
async def test_fetch_release_info_uses_httpx_client_with_env_proxy_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    _reset_fake_client()
    _FakeAsyncClient.json_payload = [
        {
            "name": "AstrBot v4.23.2",
            "published_at": "2026-04-16T00:00:00Z",
            "body": "fix updater socks proxy support",
            "tag_name": "v4.23.2",
            "zipball_url": "https://example.com/astrbot.zip",
        }
    ]

    monkeypatch.setattr(
        zip_updator_module,
        "aiohttp",
        SimpleNamespace(
            ClientSession=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError(
                    "fetch_release_info should not use aiohttp.ClientSession"
                )
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        zip_updator_module,
        "httpx",
        SimpleNamespace(AsyncClient=_FakeAsyncClient),
        raising=False,
    )

    release_info = await RepoZipUpdator().fetch_release_info(
        "https://api.soulter.top/releases"
    )

    assert release_info == [
        {
            "version": "AstrBot v4.23.2",
            "published_at": "2026-04-16T00:00:00Z",
            "body": "fix updater socks proxy support",
            "tag_name": "v4.23.2",
            "zipball_url": "https://example.com/astrbot.zip",
        }
    ]
    assert _FakeAsyncClient.requested_urls == ["https://api.soulter.top/releases"]
    assert _FakeAsyncClient.init_kwargs is not None
    assert _FakeAsyncClient.init_kwargs["follow_redirects"] is True
    assert _FakeAsyncClient.init_kwargs["timeout"] == 30.0
    assert _FakeAsyncClient.init_kwargs["trust_env"] is True
    assert _FakeAsyncClient.init_kwargs["verify"] == certifi.where()


@pytest.mark.asyncio
async def test_download_from_repo_url_uses_httpx_stream_for_zip_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    _reset_fake_client()
    _FakeAsyncClient.stream_payload = b"zip-data"

    async def fake_fetch_release_info(self, url: str, latest: bool = True):  # noqa: ARG001
        return [
            {
                "version": "AstrBot v4.23.2",
                "published_at": "2026-04-16T00:00:00Z",
                "body": "fix updater socks proxy support",
                "tag_name": "v4.23.2",
                "zipball_url": "https://example.com/archive.zip",
            }
        ]

    monkeypatch.setattr(RepoZipUpdator, "fetch_release_info", fake_fetch_release_info)
    monkeypatch.setattr(
        zip_updator_module,
        "download_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("download_from_repo_url should not use aiohttp download_file")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        zip_updator_module,
        "httpx",
        SimpleNamespace(AsyncClient=_FakeAsyncClient),
        raising=False,
    )

    target_path = tmp_path / "AstrBot"
    await RepoZipUpdator().download_from_repo_url(
        str(target_path),
        "https://github.com/AstrBotDevs/AstrBot",
    )

    assert (tmp_path / "AstrBot.zip").read_bytes() == b"zip-data"
    assert _FakeAsyncClient.stream_urls == ["https://example.com/archive.zip"]
    assert _FakeAsyncClient.init_kwargs is not None
    assert _FakeAsyncClient.init_kwargs["follow_redirects"] is True
    assert _FakeAsyncClient.init_kwargs["timeout"] == 1800.0
    assert _FakeAsyncClient.init_kwargs["trust_env"] is True
    assert _FakeAsyncClient.init_kwargs["verify"] == certifi.where()


@pytest.mark.asyncio
async def test_fetch_release_info_logs_status_code_and_truncated_body_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    url = "https://api.soulter.top/releases"
    body = "x" * 1005
    log_messages: list[str] = []

    monkeypatch.setattr(
        RepoZipUpdator,
        "_create_httpx_client",
        staticmethod(
            lambda timeout=30.0: _FakeStatusErrorAsyncClient(  # noqa: ARG005
                _FakeStatusErrorResponse(502, body, url)
            )
        ),
    )
    monkeypatch.setattr(
        zip_updator_module.logger,
        "error",
        lambda message: log_messages.append(message),
    )

    with pytest.raises(Exception, match="解析版本信息失败"):
        await RepoZipUpdator().fetch_release_info(url)

    assert any("状态码: 502" in message for message in log_messages)
    assert any("内容: " in message for message in log_messages)
    assert any("...[truncated]" in message for message in log_messages)


@pytest.mark.asyncio
async def test_download_file_removes_partial_file_when_stream_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        RepoZipUpdator,
        "_create_httpx_client",
        staticmethod(
            lambda timeout=30.0: _FakeFailingStreamAsyncClient()  # noqa: ARG005
        ),
    )

    target_path = tmp_path / "partial.zip"

    with pytest.raises(RuntimeError, match="stream interrupted"):
        await RepoZipUpdator()._download_file(
            "https://example.com/archive.zip",
            str(target_path),
        )

    assert not target_path.exists()
